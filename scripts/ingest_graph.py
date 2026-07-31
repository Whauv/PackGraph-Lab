from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.repositories.data_store import get_data_store
from app.repositories.graph_repository import Neo4jAdminRepository
from app.services.ingest_pipeline import IngestPipeline
from app.services.ingest_sources import resolve_ingest_sources
from app.services.private_data_service import PrivateDataService


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
    parser.add_argument("--skip-generated", action="store_true", help="Skip generated PackGraph bundle ingestion.")
    parser.add_argument("--report-path", help="Write the ingest/profile report JSON to this path.")
    return parser


def main(argv: list[str] | None = None) -> dict:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    sources = resolve_ingest_sources(
        settings,
        json_source_dir=args.json_source_dir,
        sqlite_path=args.sqlite_path,
    )
    source_service = PrivateDataService(
        settings.private_data_dir,
        settings.sqlite_ingest_path,
        parser_name=settings.ingest_parser_name,
        parser_version=settings.ingest_parser_version,
    )

    started = time.perf_counter()
    profile = source_service.inspect_schema(sources.json_source_dir, sources.sqlite_path)
    local_rows = source_service.ingestable_records(sources.json_source_dir, sources.sqlite_path)
    report = {
        "status": "profiled" if args.profile_only else "pending_ingest",
        "selection_source": sources.selection_source,
        "json_source_dir": str(sources.json_source_dir) if sources.json_source_dir else None,
        "sqlite_path": str(sources.sqlite_path) if sources.sqlite_path else None,
        "profile": profile,
        "private_records": len(local_rows),
    }

    if args.profile_only:
        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        _emit_report(report, args.report_path)
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
        metrics["external"] = pipeline.ingest_external_records([normalize_neo4j_properties(row) for row in local_rows])

        report.update(
            {
                "status": "ok",
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "counts": store["manifest"]["counts"],
                "metrics": metrics,
            }
        )
        _emit_report(report, args.report_path)
        print(report)
        return report
    finally:
        if repo:
            repo.close()


def _emit_report(report: dict, report_path: str | None) -> None:
    if not report_path:
        return
    Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")


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
