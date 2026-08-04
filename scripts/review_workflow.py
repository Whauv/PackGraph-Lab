from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.core.runtime_db import build_runtime_db
from app.services.agent_review import ReviewCandidateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize, export, and import PackGraph review decisions.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("summary", help="Show review summary counts.")

    export_parser = subparsers.add_parser("export", help="Export pending review items using safe fields by default.")
    export_parser.add_argument("--output", required=True, help="Destination JSON or CSV path.")
    export_parser.add_argument("--include-raw-props", action="store_true", help="Opt in to raw review payloads in export output.")

    import_parser = subparsers.add_parser("import", help="Import reviewed decisions.")
    import_parser.add_argument("--input", required=True, help="Reviewed decision JSON path.")
    import_parser.add_argument("--apply", action="store_true", help="Apply reviewed match decisions to the persistent cache.")
    return parser


def main(argv: list[str] | None = None) -> dict:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    store = ReviewCandidateStore(settings, build_runtime_db(settings))
    if args.command == "summary":
        payload = store.summary()
    elif args.command == "export":
        payload = store.export_pending(Path(args.output), include_raw_props=args.include_raw_props)
    else:
        payload = store.import_reviewed_decisions(Path(args.input), apply=args.apply)
    print(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    main()
