from __future__ import annotations

import argparse
from datetime import datetime, UTC
from collections import Counter
import json
import time
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.repositories.data_store import get_data_store
from app.repositories.graph_repository import Neo4jAdminRepository
from app.services.ingest_pipeline import IngestPipeline
from app.services.ingest_sources import resolve_ingest_sources
from app.services.private_data_service import PrivateDataService
from app.services.security_utils import sanitize_private_record_for_graph, sanitize_run_report, secure_write_json


CONSTRAINTS = [
    "CREATE CONSTRAINT material_id IF NOT EXISTS FOR (m:Material) REQUIRE m.material_id IS UNIQUE",
    "CREATE CONSTRAINT supplier_id IF NOT EXISTS FOR (s:Supplier) REQUIRE s.supplier_id IS UNIQUE",
    "CREATE CONSTRAINT application_id IF NOT EXISTS FOR (a:Application) REQUIRE a.application_id IS UNIQUE",
    "CREATE CONSTRAINT regulation_id IF NOT EXISTS FOR (r:Regulation) REQUIRE r.regulation_id IS UNIQUE",
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:SourceDocument) REQUIRE d.document_id IS UNIQUE",
    "CREATE CONSTRAINT private_record_id IF NOT EXISTS FOR (p:PrivateRecord) REQUIRE p.private_record_id IS UNIQUE",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest PackGraph Lab demo data and local JSON/SQLite sources into Neo4j.")
    parser.add_argument("--json-source-dir", help="Override the JSON ingest directory. Scans subfolders recursively.")
    parser.add_argument("--sqlite-path", help="Optional SQLite database path to profile and ingest.")
    parser.add_argument("--profile-only", action="store_true", help="Only profile local sources without writing to Neo4j.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve, profile, and prepare ingest rows without writing to Neo4j.")
    parser.add_argument("--skip-generated", action="store_true", help="Skip generated PackGraph bundle ingestion.")
    parser.add_argument("--max-files", type=int, help="Process at most this many JSON files from the local source folder.")
    parser.add_argument("--report-path", help="Write the ingest/profile report JSON to this path.")
    parser.add_argument("--resume-run-id", help="Resume source selection and reporting from an earlier run ID.")
    parser.add_argument("--role", choices=["read", "review", "write", "admin"], default="write", help="Operator role for this command.")
    return parser


def main(argv: list[str] | None = None) -> dict:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    run_id = args.resume_run_id or f"ING-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6].upper()}"
    _enforce_role(args.role, args.profile_only, args.dry_run)
    state_path = settings.ingest_state_dir / f"{run_id}.json"

    resumed_state = _load_state(state_path) if args.resume_run_id else {}
    if args.resume_run_id and resumed_state.get("selection_source") == "cli" and not args.json_source_dir and not args.sqlite_path:
        raise ValueError("Resumed runs from sanitized CLI state must be given --json-source-dir and/or --sqlite-path again because raw local paths are not stored in run-state files.")
    sources = resolve_ingest_sources(
        settings,
        json_source_dir=args.json_source_dir or resumed_state.get("json_source_dir"),
        sqlite_path=args.sqlite_path or resumed_state.get("sqlite_path"),
    )
    source_service = PrivateDataService(
        settings.private_data_dir,
        settings.sqlite_ingest_path,
        parser_name=settings.ingest_parser_name,
        parser_version=settings.ingest_parser_version,
        schema_version=settings.ingest_schema_version,
        transform_cache_path=settings.transform_cache_path,
    )

    started = time.perf_counter()
    profile = source_service.inspect_schema(sources.json_source_dir, sources.sqlite_path, max_files=args.max_files)
    local_rows = source_service.ingestable_records(
        sources.json_source_dir,
        sources.sqlite_path,
        run_id=run_id,
        max_files=args.max_files,
    )
    local_rows, dedup_summary = _deduplicate_rows(local_rows)
    report_path = Path(args.report_path) if args.report_path else settings.ingest_report_dir / f"{run_id}.json"
    report = {
        "run_id": run_id,
        "status": "profiled" if args.profile_only else "pending_ingest",
        "write_mode": "profile_only" if args.profile_only else "dry_run" if args.dry_run else "write",
        "resumed_from": args.resume_run_id,
        "operator_role": args.role,
        "role_scope_note": "CLI role checks are advisory safeguards only and are not authentication or authorization boundaries.",
        "selection_source": sources.selection_source,
        "json_source_dir": str(sources.json_source_dir) if sources.json_source_dir else None,
        "sqlite_path": str(sources.sqlite_path) if sources.sqlite_path else None,
        "profile": profile,
        "private_records": len(local_rows),
        "duplicate_counts": {
            "schema_duplicate_groups": len(profile["source_profile"].get("duplicate_content_report", [])),
            "prewrite_duplicates_removed": dedup_summary["duplicates_removed"],
        },
        "file_level_results": profile["source_profile"].get("file_results", []),
        "artifact_paths": {
            "report_path": str(report_path),
            "state_path": str(state_path),
        },
        "backend_mode": _backend_summary(settings),
        "graph_summary": {
            "graph_backend": settings.graph_backend,
            "graph_schema_version": settings.graph_schema_version,
        },
    }
    _write_state(state_path, report)

    if args.profile_only:
        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        report["duration_seconds"] = report["elapsed_seconds"]
        report["completed_at"] = datetime.now(UTC).isoformat()
        _write_state(state_path, report)
        _emit_report(report, report_path)
        print(report)
        return report

    if args.dry_run:
        report.update(
            {
                "status": "dry_run_complete",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "duration_seconds": round(time.perf_counter() - started, 3),
                "graph_summary": {
                    **report["graph_summary"],
                    "external_private_records_ready": len(local_rows),
                    "generated_bundle_ready": 0 if args.skip_generated else 1,
                },
                "completed_at": datetime.now(UTC).isoformat(),
            }
        )
        _write_state(state_path, report)
        _emit_report(report, report_path)
        print(report)
        return report

    store = get_data_store().load_bundle()
    repo = None
    try:
        repo = connect_with_retry(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)
        for query in CONSTRAINTS:
            repo.run(query)

        pipeline = IngestPipeline(repo)
        metrics = {"generated": {"nodes": {}, "edges": {}}, "external": {"nodes": {}, "edges": {}}}
        if not args.skip_generated:
            metrics["generated"] = pipeline.ingest_generated_bundle(store, normalize_neo4j_properties)
        metrics["external"] = pipeline.ingest_external_records(
            [normalize_neo4j_properties(sanitize_private_record_for_graph(row)) for row in local_rows]
        )

        report.update(
            {
                "status": "ok",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "duration_seconds": round(time.perf_counter() - started, 3),
                "completed_at": datetime.now(UTC).isoformat(),
                "counts": store["manifest"]["counts"],
                "metrics": metrics,
                "graph_summary": {
                    **report["graph_summary"],
                    "counts": store["manifest"]["counts"],
                    "metrics": metrics,
                },
            }
        )
        _write_state(state_path, report)
        _emit_report(report, report_path)
        print(report)
        return report
    finally:
        if repo:
            repo.close()


def _emit_report(report: dict, report_path: Path) -> None:
    secure_write_json(report_path, sanitize_run_report(report))


def _write_state(state_path: Path, report: dict) -> None:
    secure_write_json(state_path, sanitize_run_report(report))


def _load_state(state_path: Path) -> dict:
    if not state_path.exists():
        raise FileNotFoundError(f"Run state not found for resume: {state_path}")
    return json.loads(state_path.read_text(encoding="utf-8"))


def _backend_summary(settings) -> dict:
    return {
        "llm_enabled": settings.llm_enabled,
        "llm_backend": settings.llm_backend,
        "embeddings_backend": settings.embeddings_backend,
        "er_backend": settings.er_backend,
        "adjudicator_backend": settings.adjudicator_backend,
        "neo4j_uri": _redact_connection(settings.neo4j_uri),
        "neo4j_database": settings.neo4j_database,
    }


def _redact_connection(uri: str) -> str:
    if "://" not in uri:
        return "***"
    scheme, rest = uri.split("://", 1)
    host = rest.split("@")[-1]
    return f"{scheme}://{host}"


def _enforce_role(role: str, profile_only: bool, dry_run: bool) -> None:
    if profile_only or dry_run:
        return
    if role not in {"write", "admin"}:
        raise PermissionError("Write ingest requires operator role 'write' or 'admin'. This CLI role flag is advisory only, not real authentication.")


def _deduplicate_rows(rows: list[dict]) -> tuple[list[dict], dict[str, int]]:
    unique_rows = []
    seen = set()
    duplicates_removed = 0
    for row in rows:
        dedupe_key = (row.get("private_record_id"), row.get("content_hash"))
        if dedupe_key in seen:
            duplicates_removed += 1
            continue
        seen.add(dedupe_key)
        unique_rows.append(row)
    return unique_rows, {"duplicates_removed": duplicates_removed}


def connect_with_retry(uri: str, username: str, password: str, attempts: int = 30, delay_seconds: float = 2.0) -> Neo4jAdminRepository:
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            repo = Neo4jAdminRepository(uri, username, password)
            repo.run("RETURN 1 AS ok")
            return repo
        except Exception as exc:  # pragma: no cover - startup retry path
            last_error = exc
            print(f"Waiting for Neo4j ({attempt}/{attempts}) at {uri} ...")
            time.sleep(delay_seconds)
    raise RuntimeError(f"Neo4j was not ready after {attempts} attempts.") from last_error


def normalize_neo4j_properties(row: dict) -> dict:
    normalized = {}
    for key, value in row.items():
        if isinstance(value, dict):
            for nested_key, nested_value in flatten_nested_dict(value, prefix=key).items():
                normalized[nested_key] = normalize_scalar_or_list(nested_value)
        else:
            normalized[key] = normalize_scalar_or_list(value)
    return normalized


def flatten_nested_dict(value: dict, prefix: str) -> dict:
    flattened = {}
    for nested_key, nested_value in value.items():
        composite_key = f"{prefix}_{nested_key}"
        if isinstance(nested_value, dict):
            flattened.update(flatten_nested_dict(nested_value, composite_key))
        else:
            flattened[composite_key] = nested_value
    return flattened


def normalize_scalar_or_list(value):
    if isinstance(value, list):
        if all(isinstance(item, (str, int, float, bool)) or item is None for item in value):
            return value
        return json.dumps(value, sort_keys=True)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return json.dumps(value, sort_keys=True)


def cli_main() -> None:
    main()


if __name__ == "__main__":
    cli_main()
