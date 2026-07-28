from __future__ import annotations

from datetime import datetime, UTC
import json
from typing import Any
from uuid import uuid4

from app.core.config import Settings


class ReviewCandidateStore:
    def __init__(self, settings: Settings):
        self.path = settings.review_candidates_path

    def list(self) -> list[dict[str, Any]]:
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

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
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(records, handle, indent=2)
        return record
