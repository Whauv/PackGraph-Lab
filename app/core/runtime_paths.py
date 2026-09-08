from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.security_utils import secure_mkdir


@dataclass(frozen=True)
class RuntimePaths:
    generated_dir: Path
    runtime_dir: Path
    staging_dir: Path
    reports_dir: Path
    ingest_state_dir: Path
    runtime_db_path: Path
    project_memory_path: Path
    review_candidates_path: Path

    @classmethod
    def from_settings(cls, settings: Any) -> "RuntimePaths":
        return cls(
            generated_dir=settings.packgraph_data_dir,
            runtime_dir=settings.packgraph_runtime_dir,
            staging_dir=settings.packgraph_staging_dir,
            reports_dir=settings.ingest_report_dir,
            ingest_state_dir=settings.ingest_state_dir,
            runtime_db_path=settings.runtime_db_path,
            project_memory_path=settings.project_memory_path,
            review_candidates_path=settings.review_candidates_path,
        )

    def ensure_directories(self) -> None:
        for path in [
            self.generated_dir,
            self.runtime_dir,
            self.staging_dir,
            self.reports_dir,
            self.ingest_state_dir,
            self.runtime_db_path.parent,
            self.project_memory_path.parent,
            self.review_candidates_path.parent,
        ]:
            secure_mkdir(path)

    def documentation_summary(self) -> dict[str, str]:
        return {
            "source_controlled_seed_data": str(self.generated_dir),
            "local_runtime_artifacts": str(self.runtime_dir),
            "local_staging_artifacts": str(self.staging_dir),
            "ingest_reports": str(self.reports_dir),
            "ingest_resume_state": str(self.ingest_state_dir),
        }
