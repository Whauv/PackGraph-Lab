from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4


class InvestigationService:
    def __init__(self, runtime_dir: Path):
        self.path = runtime_dir / "investigations.json"

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, investigations: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(investigations, handle, indent=2)

    def ensure_seed(self, seed_data: list[dict[str, Any]]) -> None:
        if not self.path.exists():
            self._write(seed_data)

    def list(self) -> list[dict[str, Any]]:
        return self._read()

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        investigations = self._read()
        record = {"investigation_id": f"INV-{uuid4().hex[:8].upper()}", "status": "open", **payload}
        investigations.append(record)
        self._write(investigations)
        return record
