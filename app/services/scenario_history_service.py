from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4


class ScenarioHistoryService:
    def __init__(self, runtime_dir: Path):
        self.path = runtime_dir / "scenario_history.json"

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(records, handle, indent=2)

    def list(self, owner_id: str | None = None) -> list[dict[str, Any]]:
        records = self._read()
        if owner_id:
            records = [item for item in records if item.get("owner_id") in {None, owner_id}]
        return list(reversed(records))

    def save(
        self,
        *,
        scenario_type: str,
        material_id: str | None,
        supplier_id: str | None,
        options: dict[str, Any],
        result: dict[str, Any],
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        records = self._read()
        before = {
            "material_id": material_id,
            "supplier_id": supplier_id,
            "options": options,
        }
        after = {
            "summary": result.get("summary"),
            "metrics": result.get("metrics", {}),
            "actions": result.get("actions", []),
            "impact_count": len(result.get("impacts", [])),
        }
        record = {
            "scenario_run_id": f"SCN-{uuid4().hex[:8].upper()}",
            "owner_id": owner_id,
            "scenario_type": scenario_type,
            "before": before,
            "after": after,
            "result": result,
        }
        records.append(record)
        self._write(records)
        return record
