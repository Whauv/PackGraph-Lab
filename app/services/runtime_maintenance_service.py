from __future__ import annotations

from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Any

from app.core.config import Settings


class RuntimeMaintenanceService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def summary(self) -> dict[str, Any]:
        return {
            "profile": self.settings.runtime_profile,
            "retention_days": self.settings.cleanup_retention_days,
            "paths": {
                "runtime": str(self.settings.packgraph_runtime_dir),
                "staging": str(self.settings.packgraph_staging_dir),
                "reports": str(self.settings.ingest_report_dir),
            },
            "runtime": self._dir_summary(self.settings.packgraph_runtime_dir),
            "staging": self._dir_summary(self.settings.packgraph_staging_dir),
            "reports": self._dir_summary(self.settings.ingest_report_dir),
        }

    def cleanup(self) -> dict[str, Any]:
        removed = []
        removed.extend(self._trim_directory(self.settings.ingest_report_dir, self.settings.cleanup_max_report_files))
        removed.extend(self._trim_runtime_logs(self.settings.packgraph_runtime_dir, self.settings.cleanup_max_runtime_logs))
        removed.extend(self._remove_old_temp_files(self.settings.packgraph_runtime_dir, self.settings.cleanup_retention_days))
        return {"removed": removed, "removed_count": len(removed), "summary": self.summary()}

    def _dir_summary(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"exists": False, "file_count": 0, "total_bytes": 0}
        files = [item for item in path.rglob("*") if item.is_file()]
        total_bytes = sum(item.stat().st_size for item in files)
        return {"exists": True, "file_count": len(files), "total_bytes": total_bytes}

    def _trim_directory(self, path: Path, keep: int) -> list[str]:
        files = sorted([item for item in path.glob("*") if item.is_file()], key=lambda item: item.stat().st_mtime, reverse=True)
        removed = []
        for item in files[keep:]:
            item.unlink(missing_ok=True)
            removed.append(str(item))
        return removed

    def _trim_runtime_logs(self, path: Path, keep: int) -> list[str]:
        files = sorted(
            [item for item in path.glob("*.jsonl") if item.is_file()],
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        removed = []
        for item in files[keep:]:
            item.unlink(missing_ok=True)
            removed.append(str(item))
        return removed

    def _remove_old_temp_files(self, path: Path, retention_days: int) -> list[str]:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        removed = []
        for item in path.rglob("*"):
            if not item.is_file():
                continue
            if not item.name.endswith((".tmp", ".bak", ".partial")):
                continue
            modified = datetime.fromtimestamp(item.stat().st_mtime, UTC)
            if modified < cutoff:
                item.unlink(missing_ok=True)
                removed.append(str(item))
        return removed
