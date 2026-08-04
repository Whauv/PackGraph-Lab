from __future__ import annotations

from collections import Counter
from datetime import datetime, UTC
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.core.runtime_db import RuntimeDatabase, deserialize_json, serialize_json
from app.services.entity_resolution_agent import MatchDecisionCache
from app.services.security_utils import review_export_to_csv_bytes, safe_path_hint, sanitize_audit_payload, sanitize_review_payload, secure_append_jsonl, secure_write_json, secure_write_text


class ReviewCandidateStore:
    def __init__(self, settings: Settings, runtime_db: RuntimeDatabase):
        self.settings = settings
        self.db = runtime_db
        self.audit_path = settings.review_audit_path
        self.cache = MatchDecisionCache(settings.match_decision_cache_path)

    def list(self, status: str | None = None, org_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        query = "SELECT * FROM review_candidates"
        params: tuple[Any, ...] = ()
        conditions = []
        if status:
            conditions.append("status=?")
            params = (*params, status)
        if org_id:
            conditions.append("org_id=?")
            params = (*params, org_id)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params = (*params, limit)
        with self.db.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_candidate(row) for row in rows]

    def get(self, candidate_id: str, org_id: str | None = None) -> dict[str, Any] | None:
        with self.db.connect() as connection:
            if org_id:
                row = connection.execute(
                    "SELECT * FROM review_candidates WHERE candidate_id=? AND org_id=?",
                    (candidate_id, org_id),
                ).fetchone()
            else:
                row = connection.execute("SELECT * FROM review_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
        return self._row_to_candidate(row) if row else None

    def summary(self, org_id: str | None = None) -> dict[str, Any]:
        records = self.list(org_id=org_id, limit=1000)
        by_status = Counter(record["status"] for record in records)
        by_type = Counter(record["candidate_type"] for record in records)
        by_assignee = Counter(record.get("assigned_reviewer_id") or "unassigned" for record in records if record["status"] != "closed")
        return {
            "total": len(records),
            "by_status": dict(sorted(by_status.items())),
            "by_type": dict(sorted(by_type.items())),
            "by_assignee": dict(sorted(by_assignee.items())),
            "pending": sum(1 for record in records if record["status"] in {"pending_human_review", "assigned", "in_approval"}),
        }

    def create(self, candidate_type: str, reason: str, payload: dict[str, Any], org_id: str = "ORG-001") -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        sanitized_payload = sanitize_review_payload(payload, include_raw_props=True)
        record = {
            "candidate_id": f"ARC-{uuid4().hex[:10].upper()}",
            "org_id": org_id,
            "candidate_type": candidate_type,
            "reason": reason,
            "status": "pending_human_review",
            "review_before_writeback": 1,
            "payload_json": serialize_json(sanitized_payload),
            "assigned_reviewer_id": None,
            "decision_state": "new",
            "created_at": now,
            "updated_at": now,
        }
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO review_candidates (
                    candidate_id, candidate_type, reason, status, review_before_writeback,
                    payload_json, assigned_reviewer_id, decision_state, created_at, updated_at, org_id
                ) VALUES (
                    :candidate_id, :candidate_type, :reason, :status, :review_before_writeback,
                    :payload_json, :assigned_reviewer_id, :decision_state, :created_at, :updated_at, :org_id
                )
                """,
                record,
            )
        self._history(record["candidate_id"], org_id, None, "created", "", {"reason": reason})
        self._append_audit("created", record)
        return self.get(record["candidate_id"], org_id=org_id)

    def assign(self, candidate_id: str, reviewer_id: str, actor_id: str | None, org_id: str) -> dict[str, Any] | None:
        now = datetime.now(UTC).isoformat()
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE review_candidates SET assigned_reviewer_id=?, status='assigned', decision_state='assigned', updated_at=? WHERE candidate_id=? AND org_id=?",
                (reviewer_id, now, candidate_id, org_id),
            )
        candidate = self.get(candidate_id, org_id=org_id)
        if candidate:
            self._history(candidate_id, org_id, actor_id, "assigned", "", {"reviewer_id": reviewer_id})
        return candidate

    def comment(self, candidate_id: str, actor_id: str | None, comment: str, org_id: str) -> dict[str, Any] | None:
        candidate = self.get(candidate_id, org_id=org_id)
        if not candidate:
            return None
        self._history(candidate_id, org_id, actor_id, "commented", comment, {})
        return candidate

    def decide(self, candidate_id: str, actor_id: str | None, status: str, comment: str, metadata: dict[str, Any] | None = None, org_id: str = "ORG-001") -> dict[str, Any] | None:
        now = datetime.now(UTC).isoformat()
        metadata = metadata or {}
        decision_state = "approved" if status == "approved" else "rejected" if status == "rejected" else "in_approval"
        stored_status = "closed" if status in {"approved", "rejected"} else status
        with self.db.connect() as connection:
            connection.execute(
                "UPDATE review_candidates SET status=?, decision_state=?, updated_at=? WHERE candidate_id=? AND org_id=?",
                (stored_status, decision_state, now, candidate_id, org_id),
            )
        candidate = self.get(candidate_id, org_id=org_id)
        if candidate:
            self._history(candidate_id, org_id, actor_id, status, comment, metadata)
        if status == "approved" and metadata.get("match_pair_key") and metadata.get("resolution_decision"):
            self.cache.set(
                metadata["match_pair_key"],
                {
                    "left_label": metadata.get("left_label", ""),
                    "right_label": metadata.get("right_label", ""),
                    "confidence": float(metadata.get("confidence", 1.0)),
                    "decision": metadata["resolution_decision"],
                    "reason": comment or "Approved review decision.",
                },
            )
        return candidate

    def history(self, candidate_id: str, org_id: str | None = None) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            if org_id:
                rows = connection.execute(
                    "SELECT * FROM review_history WHERE candidate_id=? AND org_id=? ORDER BY created_at ASC",
                    (candidate_id, org_id),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM review_history WHERE candidate_id=? ORDER BY created_at ASC",
                    (candidate_id,),
                ).fetchall()
        return [
            {
                **dict(row),
                "metadata": deserialize_json(row["metadata_json"], {}),
            }
            for row in rows
        ]

    def export_pending(self, destination: Path, org_id: str | None = None, *, include_raw_props: bool = False) -> dict[str, Any]:
        pending = [
            self._format_pending_export(record, include_raw_props=include_raw_props)
            for record in self.list(org_id=org_id, limit=1000)
            if record["status"] in {"pending_human_review", "assigned", "in_approval"}
        ]
        if destination.suffix.lower() == ".csv":
            secure_write_text(destination, review_export_to_csv_bytes(pending).decode("utf-8"))
        else:
            secure_write_json(destination, pending)
        self._append_audit("exported_pending", {"destination": str(destination), "count": len(pending), "include_raw_props": include_raw_props})
        return {"destination": safe_path_hint(destination), "count": len(pending), "format": destination.suffix.lower().lstrip(".") or "json", "include_raw_props": include_raw_props}

    def import_reviewed_decisions(self, source: Path, apply: bool = False, org_id: str | None = None) -> dict[str, Any]:
        payload = json.loads(source.read_text(encoding="utf-8"))
        applied = 0
        for decision in payload:
            candidate_id = decision.get("candidate_id")
            candidate_org_id = org_id or decision.get("org_id") or "ORG-001"
            if not candidate_id or not self.get(candidate_id, org_id=candidate_org_id):
                continue
            self.decide(
                candidate_id=candidate_id,
                actor_id=decision.get("reviewer_id"),
                status=decision.get("status", "approved"),
                comment=decision.get("review_notes", ""),
                metadata=decision if apply else {},
                org_id=candidate_org_id,
            )
            applied += 1
        self._append_audit("imported_reviewed_decisions", {"source": str(source), "applied": applied, "apply": apply})
        return {"source": safe_path_hint(source), "applied": applied, "apply": apply}

    def _history(self, candidate_id: str, org_id: str, actor_id: str | None, action: str, comment: str, metadata: dict[str, Any]) -> None:
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO review_history (history_id, candidate_id, org_id, actor_id, action, comment, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"RVH-{uuid4().hex[:10].upper()}",
                    candidate_id,
                    org_id,
                    actor_id,
                    action,
                    comment,
                    serialize_json(metadata),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def _row_to_candidate(self, row: Any) -> dict[str, Any]:
        record = dict(row)
        raw_payload = deserialize_json(record["payload_json"], {})
        return {
            **record,
            "review_before_writeback": bool(record["review_before_writeback"]),
            "payload": sanitize_review_payload(raw_payload, include_raw_props=False),
            "history": self.history(record["candidate_id"], org_id=record.get("org_id")),
        }

    def _append_audit(self, action: str, payload: dict[str, Any]) -> None:
        entry = sanitize_audit_payload({"timestamp": datetime.now(UTC).isoformat(), "action": action, **payload})
        secure_append_jsonl(self.audit_path, entry)

    def _format_pending_export(self, record: dict[str, Any], *, include_raw_props: bool = False) -> dict[str, Any]:
        payload = self._load_raw_payload(record["candidate_id"], record.get("org_id"))
        history = record.get("history", [])
        comparison = payload.get("comparison", {})
        return {
            "candidate_id": record["candidate_id"],
            "org_id": record["org_id"],
            "candidate_type": record["candidate_type"],
            "reason": record["reason"],
            "status": record["status"],
            "review_before_writeback": record["review_before_writeback"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "display_name": payload.get("display_name")
            or comparison.get("left_label")
            or comparison.get("right_label")
            or record["candidate_id"],
            "reviewer_fields": {
                "assigned_reviewer_id": record.get("assigned_reviewer_id"),
                "decision_state": record.get("decision_state"),
                "last_updated_at": record.get("updated_at"),
            },
            "provenance_snippets": payload.get("provenance_snippets", []),
            "score_breakdown": comparison.get("score_breakdown") or payload.get("score_breakdown") or {},
            "audit_payload": {
                "reason": record.get("reason"),
                "history_events": len(history),
                "latest_history": {
                    "action": history[-1].get("action"),
                    "comment": history[-1].get("comment"),
                    "created_at": history[-1].get("created_at"),
                }
                if history
                else None,
            },
            "payload": sanitize_review_payload(payload, include_raw_props=include_raw_props),
        }

    def _load_raw_payload(self, candidate_id: str, org_id: str | None) -> dict[str, Any]:
        with self.db.connect() as connection:
            if org_id:
                row = connection.execute(
                    "SELECT payload_json FROM review_candidates WHERE candidate_id=? AND org_id=?",
                    (candidate_id, org_id),
                ).fetchone()
            else:
                row = connection.execute(
                    "SELECT payload_json FROM review_candidates WHERE candidate_id=?",
                    (candidate_id,),
                ).fetchone()
        return deserialize_json(row["payload_json"], {}) if row else {}
