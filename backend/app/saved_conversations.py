"""Local owner access: python -m app.saved_conversations list|show|delete."""

import argparse
import json
import sqlite3

from .config import Settings
from .conversation_store import ConversationStore


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect privately archived conversations.")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--limit", type=int, default=20)
    listing.add_argument("--offset", type=int, default=0)
    for command in ("show", "delete"):
        commands.add_parser(command).add_argument("id")
    args = parser.parse_args(argv)
    store = ConversationStore(Settings().resolved_job_storage_path)
    try:
        store.initialize()
        if args.command == "list":
            print(json.dumps(store.list_conversations(args.limit, args.offset), indent=2, ensure_ascii=True))
        elif args.command == "show":
            result = store.get_conversation(args.id)
            if result is None:
                parser.exit(1, "Conversation not found.\n")
            print(json.dumps(result, indent=2, ensure_ascii=True))
        elif not store.delete_conversation(args.id):
            parser.exit(1, "Conversation not found.\n")
        else:
            print("Deleted conversation and its messages.")
    except (OSError, sqlite3.Error, ValueError) as exc:
        parser.exit(1, f"Archive command failed: {exc}\n")


if __name__ == "__main__":
    main()
