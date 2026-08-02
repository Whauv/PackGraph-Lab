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
    parser = argparse.ArgumentParser(description="Show a local-first operator status summary for PackGraph Lab.")
    parser.add_argument("--limit", type=int, default=5, help="Number of recent ingest reports to include.")
    return parser


def main(argv: list[str] | None = None) -> dict:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    review_store = ReviewCandidateStore(settings, build_runtime_db(settings))
    reports = _load_recent_reports(settings.ingest_report_dir, args.limit)
    payload = {
        "backend_mode": {
            "graph_backend": settings.graph_backend,
            "llm_enabled": settings.llm_enabled,
            "llm_backend": settings.llm_backend,
            "embeddings_backend": settings.embeddings_backend,
            "er_backend": settings.er_backend,
            "adjudicator_backend": settings.adjudicator_backend,
            "neo4j_uri": _redact_connection(settings.neo4j_uri),
            "neo4j_database": settings.neo4j_database,
        },
        "artifact_locations": {
            "reports": str(settings.ingest_report_dir),
            "ingest_state": str(settings.ingest_state_dir),
            "review_audit": str(settings.review_audit_path),
            "entity_resolution_audit": str(settings.entity_resolution_audit_path),
            "runtime_db": str(settings.runtime_db_path),
        },
        "recent_run_reports": reports,
        "ingest_stats": _aggregate_ingest_stats(reports),
        "er_stats": _entity_resolution_stats(settings.entity_resolution_audit_path),
        "review_queue": review_store.summary(),
    }
    print(json.dumps(payload, indent=2))
    return payload


def _load_recent_reports(report_dir: Path, limit: int) -> list[dict]:
    report_paths = sorted(report_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)[: max(0, limit)]
    reports = []
    for path in report_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        reports.append(
            {
                "run_id": payload.get("run_id"),
                "status": payload.get("status"),
                "write_mode": payload.get("write_mode"),
                "private_records": payload.get("private_records", 0),
                "duplicate_counts": payload.get("duplicate_counts", {}),
                "duration_seconds": payload.get("duration_seconds"),
                "report_path": str(path),
            }
        )
    return reports


def _aggregate_ingest_stats(reports: list[dict]) -> dict:
    return {
        "recent_runs": len(reports),
        "recent_private_records": sum(report.get("private_records", 0) for report in reports),
        "recent_prewrite_duplicates_removed": sum(
            report.get("duplicate_counts", {}).get("prewrite_duplicates_removed", 0) for report in reports
        ),
    }


def _entity_resolution_stats(audit_path: Path) -> dict:
    if not audit_path.exists():
        return {"records": 0, "by_decision": {}}
    by_decision: dict[str, int] = {}
    record_count = 0
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record_count += 1
        payload = json.loads(line)
        decision = payload.get("decision", "unknown")
        by_decision[decision] = by_decision.get(decision, 0) + 1
    return {"records": record_count, "by_decision": dict(sorted(by_decision.items()))}


def _redact_connection(uri: str) -> str:
    if "://" not in uri:
        return "***"
    scheme, rest = uri.split("://", 1)
    host = rest.split("@")[-1]
    return f"{scheme}://{host}"


if __name__ == "__main__":
    main()
