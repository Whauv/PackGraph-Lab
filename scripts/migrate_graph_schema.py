from __future__ import annotations

import argparse
from datetime import datetime, UTC
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.core.runtime_db import build_runtime_db, serialize_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record or inspect PackGraph graph schema version metadata.")
    parser.add_argument("--apply", action="store_true", help="Record the configured graph schema version in the runtime database.")
    parser.add_argument("--notes", default="{}", help="JSON string with migration notes.")
    return parser


def main(argv: list[str] | None = None) -> dict:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    db = build_runtime_db(settings)
    if args.apply:
        notes = json.loads(args.notes)
        payload = {
            "graph_schema_version": settings.graph_schema_version,
            "applied_at": datetime.now(UTC).isoformat(),
            "notes_json": serialize_json(notes),
        }
        with db.connect() as connection:
            connection.execute(
                """
                INSERT INTO graph_schema_metadata (graph_schema_version, applied_at, notes_json)
                VALUES (:graph_schema_version, :applied_at, :notes_json)
                ON CONFLICT(graph_schema_version)
                DO UPDATE SET applied_at=excluded.applied_at, notes_json=excluded.notes_json
                """,
                payload,
            )
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT graph_schema_version, applied_at, notes_json FROM graph_schema_metadata ORDER BY applied_at DESC"
        ).fetchall()
    result = {
        "current_graph_schema_version": settings.graph_schema_version,
        "records": [
            {
                "graph_schema_version": row["graph_schema_version"],
                "applied_at": row["applied_at"],
                "notes": json.loads(row["notes_json"]),
            }
            for row in rows
        ],
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
