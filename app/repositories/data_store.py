from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.data_generator import ensure_generated_data


class DataStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    def _load_json(self, name: str) -> Any:
        path = self.data_dir / f"{name}.json"
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def load_bundle(self) -> dict[str, Any]:
        return {
            "materials": self._load_json("materials"),
            "suppliers": self._load_json("suppliers"),
            "applications": self._load_json("applications"),
            "regulations": self._load_json("regulations"),
            "certifications": self._load_json("certifications"),
            "recycling_streams": self._load_json("recycling_streams"),
            "regions": self._load_json("regions"),
            "industries": self._load_json("industries"),
            "source_documents": self._load_json("source_documents"),
            "test_reports": self._load_json("test_reports"),
            "quarterly_snapshots": self._load_json("quarterly_snapshots"),
            "investigations": self._load_json("investigations_seed"),
            "relationships": self._load_json("relationships"),
            "manifest": self._load_json("manifest"),
        }


@lru_cache
def get_data_store() -> DataStore:
    settings = get_settings()
    ensure_generated_data(settings.packgraph_data_dir)
    return DataStore(settings.packgraph_data_dir)
