from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings


@dataclass
class IngestSourceSelection:
    json_source_dir: Path | None
    sqlite_path: Path | None
    selection_source: str


def resolve_ingest_sources(
    settings: Settings,
    *,
    json_source_dir: str | Path | None = None,
    sqlite_path: str | Path | None = None,
) -> IngestSourceSelection:
    if json_source_dir is not None:
        return IngestSourceSelection(Path(json_source_dir), Path(sqlite_path) if sqlite_path else settings.sqlite_ingest_path, "cli")
    if sqlite_path is not None:
        return IngestSourceSelection(settings.json_ingest_dir, Path(sqlite_path), "cli")
    return IngestSourceSelection(settings.json_ingest_dir, settings.sqlite_ingest_path, "env")
