"""Private SQLite archive. Access is through local owner commands, never HTTP."""

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sqlite3
from uuid import uuid4


class JobStore:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError("Unsupported job archive schema version")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA secure_delete=ON")
            with connection:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS job_descriptions (
                        id TEXT PRIMARY KEY,
                        original_filename TEXT NOT NULL,
                        media_type TEXT NOT NULL,
                        byte_size INTEGER NOT NULL CHECK(byte_size > 0),
                        sha256 TEXT NOT NULL,
                        uploaded_at TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status = 'extracted'),
                        extracted_text TEXT NOT NULL,
                        original_file BLOB NOT NULL
                    )
                """)
                connection.execute("CREATE INDEX IF NOT EXISTS jobs_uploaded_at ON job_descriptions(uploaded_at)")
                connection.execute("PRAGMA user_version=1")

    def save_upload(self, filename: str, data: bytes, text: str) -> str:
        document_id = str(uuid4())
        # The filename is metadata only. It is never used as an output path.
        filename = filename.replace("\\", "/").split("/")[-1]
        suffix = Path(filename).suffix.lower()
        if len(filename) > 255:
            filename = filename[:255 - len(suffix)] + suffix
        media_type = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}[suffix]
        with closing(self._connect()) as connection, connection:
            connection.execute("""
                INSERT INTO job_descriptions
                (id, original_filename, media_type, byte_size, sha256, uploaded_at, status, extracted_text, original_file)
                VALUES (?, ?, ?, ?, ?, ?, 'extracted', ?, ?)
            """, (document_id, filename, media_type, len(data), sha256(data).hexdigest(),
                  datetime.now(timezone.utc).isoformat(), text, data))
        return document_id

    def list_uploads(self, limit: int = 20, offset: int = 0) -> list[dict]:
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError("Use a limit between 1 and 1000 and a nonnegative offset")
        with closing(self._connect()) as connection:
            rows = connection.execute("""
                SELECT id, original_filename, media_type, byte_size, sha256, uploaded_at, status
                FROM job_descriptions ORDER BY uploaded_at DESC, id DESC LIMIT ? OFFSET ?
            """, (limit, offset)).fetchall()
        return [dict(row) for row in rows]

    def get_upload(self, document_id: str, *, include_file: bool = False) -> dict | None:
        columns = "id, original_filename, media_type, byte_size, sha256, uploaded_at, status, extracted_text"
        if include_file:
            columns += ", original_file"
        with closing(self._connect()) as connection:
            row = connection.execute(f"SELECT {columns} FROM job_descriptions WHERE id = ?", (document_id,)).fetchone()
        return dict(row) if row is not None else None

    def delete_upload(self, document_id: str) -> bool:
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA secure_delete=ON")
            deleted = connection.execute("DELETE FROM job_descriptions WHERE id = ?", (document_id,)).rowcount
        return bool(deleted)
