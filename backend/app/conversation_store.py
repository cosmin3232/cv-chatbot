"""Conversation/message archive in the existing private SQLite database."""

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4


class MessageConflict(Exception):
    pass


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class ConversationStore:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'completed', 'failed')),
                    reply_to TEXT UNIQUE REFERENCES conversation_messages(id) ON DELETE CASCADE
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS messages_by_conversation ON conversation_messages(conversation_id, sequence)")

    def begin_message(self, conversation_id: str, message_id: str, prompt: str) -> str | None:
        """Save the prompt before inference; return a cached reply for an exact retry."""
        now = timestamp()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT * FROM conversation_messages WHERE id = ?", (message_id,)).fetchone()
            if existing is not None:
                if existing["conversation_id"] != conversation_id or existing["content"] != prompt or existing["role"] != "user":
                    raise MessageConflict("Message ID is already in use.")
                if existing["status"] == "completed":
                    reply = connection.execute("SELECT content FROM conversation_messages WHERE reply_to = ?", (message_id,)).fetchone()
                    if reply is None:
                        raise sqlite3.DatabaseError("Completed message is missing its reply")
                    return reply["content"]
                if existing["status"] == "pending":
                    raise MessageConflict("This message is already being processed.")
                connection.execute("UPDATE conversation_messages SET status = 'pending' WHERE id = ?", (message_id,))
            else:
                connection.execute("""INSERT INTO conversations (id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?) ON CONFLICT(id) DO NOTHING""", (conversation_id, prompt[:60], now, now))
                connection.execute("""INSERT INTO conversation_messages
                    (id, conversation_id, role, content, created_at, status) VALUES (?, ?, 'user', ?, ?, 'pending')""",
                    (message_id, conversation_id, prompt, now))
            connection.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
        return None

    def complete_message(self, conversation_id: str, message_id: str, content: str):
        now = timestamp()
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute("""UPDATE conversation_messages SET status = 'completed'
                WHERE id = ? AND conversation_id = ? AND role = 'user' AND status = 'pending'""",
                (message_id, conversation_id)).rowcount
            if changed != 1:
                raise sqlite3.DatabaseError("No pending message found")
            connection.execute("""INSERT INTO conversation_messages
                (id, conversation_id, role, content, created_at, status, reply_to)
                VALUES (?, ?, 'assistant', ?, ?, 'completed', ?)""", (str(uuid4()), conversation_id, content, now, message_id))
            connection.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))

    def fail_message(self, conversation_id: str, message_id: str):
        with closing(self._connect()) as connection, connection:
            connection.execute("""UPDATE conversation_messages SET status = 'failed'
                WHERE id = ? AND conversation_id = ? AND status = 'pending'""", (message_id, conversation_id))
            connection.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (timestamp(), conversation_id))

    def list_conversations(self, limit: int = 20, offset: int = 0) -> list[dict]:
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError("Use a limit between 1 and 1000 and a nonnegative offset")
        with closing(self._connect()) as connection:
            rows = connection.execute("""SELECT c.*, (SELECT COUNT(*) FROM conversation_messages m
                WHERE m.conversation_id = c.id) AS message_count FROM conversations c
                ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?""", (limit, offset)).fetchall()
        return [dict(row) for row in rows]

    def get_conversation(self, conversation_id: str) -> dict | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if row is None:
                return None
            messages = connection.execute("""SELECT id, role, content, created_at, status, reply_to
                FROM conversation_messages WHERE conversation_id = ? ORDER BY sequence""", (conversation_id,)).fetchall()
        return {**dict(row), "messages": [dict(message) for message in messages]}

    def delete_conversation(self, conversation_id: str) -> bool:
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA secure_delete=ON")
            return bool(connection.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,)).rowcount)
