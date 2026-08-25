from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Process queued PackGraph runtime jobs.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of queued jobs to process.")
    return parser


def main(argv: list[str] | None = None) -> dict:
    args = build_parser().parse_args(argv)
    from app.main import state

    payload = {"status": "ok", "processed": state.jobs.process_all_available(limit=args.limit)}
    print(json.dumps(payload, indent=2))
    return payload


if __name__ == "__main__":
    main()
