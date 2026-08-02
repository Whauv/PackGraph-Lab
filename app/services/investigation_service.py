from __future__ import annotations

import json
from datetime import UTC, datetime
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
            self._write([self._normalize_record(item) for item in seed_data])

    def _normalize_record(self, record: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        history = list(record.get("decision_history") or [])
        if not history:
            history = [
                {
                    "event": "created",
                    "status": record.get("status", "open"),
                    "summary": "Case created",
                    "at": record.get("created_at", now),
                }
            ]
        return {
            "status": "open",
            "owner_name": "",
            "due_date": None,
            "project_status": "active",
            "archived": False,
            "decision_history": history,
            "created_at": record.get("created_at", now),
            "updated_at": record.get("updated_at", now),
            **record,
        }

    def list(self, owner_id: str | None = None, org_id: str | None = None) -> list[dict[str, Any]]:
        investigations = [self._normalize_record(item) for item in self._read()]
        if org_id:
            investigations = [item for item in investigations if item.get("org_id", "ORG-001") == org_id]
        if owner_id:
            return [item for item in investigations if item.get("owner_id") in {None, owner_id}]
        return investigations

    def get(self, investigation_id: str, org_id: str | None = None) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in [self._normalize_record(row) for row in self._read()]
                if item["investigation_id"] == investigation_id and (org_id is None or item.get("org_id", "ORG-001") == org_id)
            ),
            None,
        )

    def create(self, payload: dict[str, Any], owner_id: str | None = None, org_id: str = "ORG-001") -> dict[str, Any]:
        investigations = self._read()
        now = datetime.now(UTC).isoformat()
        record = self._normalize_record(
            {
                "investigation_id": f"INV-{uuid4().hex[:8].upper()}",
                "status": "open",
                "owner_id": owner_id,
                "org_id": org_id,
                "created_at": now,
                "updated_at": now,
                **payload,
            }
        )
        investigations.append(record)
        self._write(investigations)
        return record

    def update(self, investigation_id: str, payload: dict[str, Any], owner_id: str | None = None, org_id: str | None = None) -> dict[str, Any] | None:
        investigations = self._read()
        for index, record in enumerate(investigations):
            if record["investigation_id"] != investigation_id:
                continue
            if org_id and record.get("org_id", "ORG-001") != org_id:
                return None
            if owner_id and record.get("owner_id") not in {None, owner_id}:
                return None
            updated = self._normalize_record(
                {
                    **record,
                    **payload,
                    "owner_id": record.get("owner_id", owner_id),
                    "org_id": record.get("org_id", org_id or "ORG-001"),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
            if (
                payload.get("status") and payload.get("status") != record.get("status")
            ) or (
                payload.get("decision_rationale") and payload.get("decision_rationale") != record.get("decision_rationale")
            ):
                updated["decision_history"] = [
                    *(record.get("decision_history") or updated.get("decision_history") or []),
                    {
                        "event": "updated",
                        "status": updated.get("status", "open"),
                        "summary": payload.get("decision_rationale") or f"Status changed to {updated.get('status', 'open')}",
                        "at": updated["updated_at"],
                    },
                ]
            investigations[index] = updated
            self._write(investigations)
            return updated
        return None
