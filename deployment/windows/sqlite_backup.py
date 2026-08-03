"""Create and verify a consistent online backup of the development SQLite DB."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination-dir", required=True, type=Path)
    args = parser.parse_args()

    source = args.source.resolve()
    destination_dir = args.destination_dir.resolve()
    if not source.is_file():
        raise SystemExit(f"SQLite database not found: {source}")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / (
        f"fof_reports_{datetime.now():%Y%m%d_%H%M%S}.db"
    )

    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as backup_db:
        source_db.backup(backup_db)
        result = backup_db.execute("PRAGMA quick_check").fetchone()
        if not result or result[0] != "ok":
            raise SystemExit(f"Backup verification failed: {result}")

    print(destination)


if __name__ == "__main__":
    main()
