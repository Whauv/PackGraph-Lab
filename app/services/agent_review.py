from __future__ import annotations

from collections import Counter
from datetime import datetime, UTC
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.services.entity_resolution_agent import MatchDecisionCache


class ReviewCandidateStore:
    def __init__(self, settings: Settings):
        self.path = settings.review_candidates_path
        self.audit_path = settings.review_audit_path
        self.cache = MatchDecisionCache(settings.match_decision_cache_path)

    def list(self) -> list[dict[str, Any]]:
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def summary(self) -> dict[str, Any]:
        records = self.list()
        by_status = Counter(record["status"] for record in records)
        by_type = Counter(record["candidate_type"] for record in records)
        return {
            "total": len(records),
            "by_status": dict(sorted(by_status.items())),
            "by_type": dict(sorted(by_type.items())),
            "pending": sum(1 for record in records if record["status"] == "pending_human_review"),
        }

    def create(self, candidate_type: str, reason: str, payload: dict[str, Any]) -> dict[str, Any]:
        records = self.list()
        record = {
            "candidate_id": f"ARC-{uuid4().hex[:10].upper()}",
            "candidate_type": candidate_type,
            "reason": reason,
            "status": "pending_human_review",
            "review_before_writeback": True,
            "created_at": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        records.append(record)
        self._write(records)
        self._append_audit("created", record)
        return record

    def export_pending(self, destination: Path) -> dict[str, Any]:
        pending = [record for record in self.list() if record["status"] == "pending_human_review"]
        destination.write_text(json.dumps(pending, indent=2), encoding="utf-8")
        self._append_audit("exported_pending", {"destination": str(destination), "count": len(pending)})
        return {"destination": str(destination), "count": len(pending)}

    def import_reviewed_decisions(self, source: Path, apply: bool = False) -> dict[str, Any]:
        payload = json.loads(source.read_text(encoding="utf-8"))
        records = self.list()
        indexed = {record["candidate_id"]: record for record in records}
        applied = 0
        for decision in payload:
            candidate_id = decision.get("candidate_id")
            if not candidate_id or candidate_id not in indexed:
                continue
            record = indexed[candidate_id]
            record["status"] = decision.get("status", record["status"])
            record["reviewed_at"] = decision.get("reviewed_at", datetime.now(UTC).isoformat())
            record["review_notes"] = decision.get("review_notes", "")
            if apply and decision.get("match_pair_key") and decision.get("resolution_decision"):
                self.cache.set(
                    decision["match_pair_key"],
                    {
                        "left_label": decision.get("left_label", ""),
                        "right_label": decision.get("right_label", ""),
                        "confidence": float(decision.get("confidence", 1.0)),
                        "decision": decision["resolution_decision"],
                        "reason": decision.get("review_notes", "Imported reviewed decision."),
                    },
                )
            applied += 1
        self._write(list(indexed.values()))
        self._append_audit("imported_reviewed_decisions", {"source": str(source), "applied": applied, "apply": apply})
        return {"source": str(source), "applied": applied, "apply": apply}

    def _write(self, records: list[dict[str, Any]]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(records, handle, indent=2)

    def _append_audit(self, action: str, payload: dict[str, Any]) -> None:
        entry = {"timestamp": datetime.now(UTC).isoformat(), "action": action, "payload": payload}
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
