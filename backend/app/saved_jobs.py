"""Owner-only CLI: python -m app.saved_jobs --help. No web routes are exposed."""

import argparse
import json
from pathlib import Path
import sqlite3

from .config import Settings
from .job_store import JobStore


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect the private local job-description archive.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    listing = subcommands.add_parser("list", help="List saved upload metadata")
    listing.add_argument("--limit", type=int, default=20)
    listing.add_argument("--offset", type=int, default=0)
    show = subcommands.add_parser("show", help="Show metadata and extracted text")
    show.add_argument("id")
    export = subcommands.add_parser("export", help="Export an original file or extracted text without overwriting")
    export.add_argument("id")
    export.add_argument("output", type=Path)
    export.add_argument("--text", action="store_true")
    delete = subcommands.add_parser("delete", help="Permanently remove one saved upload")
    delete.add_argument("id")
    args = parser.parse_args(argv)
    store = JobStore(Settings().resolved_job_storage_path)
    try:
        store.initialize()
        if args.command == "list":
            print(json.dumps(store.list_uploads(args.limit, args.offset), indent=2, ensure_ascii=True))
        elif args.command == "delete":
            if not store.delete_upload(args.id):
                parser.exit(1, "Upload not found.\n")
            print("Deleted saved upload.")
        else:
            document = store.get_upload(args.id, include_file=args.command == "export" and not args.text)
            if document is None:
                parser.exit(1, "Upload not found.\n")
            if args.command == "show":
                print(json.dumps(document, indent=2, ensure_ascii=True))
            else:
                content = document["extracted_text"].encode("utf-8") if args.text else document["original_file"]
                with args.output.open("xb") as output:
                    output.write(content)
                print(f"Exported to {args.output}")
    except (OSError, sqlite3.Error, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Archive command failed: {exc}\n")


if __name__ == "__main__":
    main()
