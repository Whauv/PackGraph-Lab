from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.core.runtime_db import RuntimeDatabase, deserialize_json, serialize_json


class GovernanceService:
    def __init__(self, settings: Settings, runtime_db: RuntimeDatabase):
        self.settings = settings
        self.db = runtime_db

    def ensure_seed(self) -> None:
        now = datetime.now(UTC).isoformat()
        with self.db.connect() as connection:
            if connection.execute("SELECT COUNT(*) AS count FROM retention_rules").fetchone()["count"] == 0:
                connection.executemany(
                    """
                    INSERT INTO retention_rules (
                        retention_policy_id, org_id, label, retention_days, applies_to, action_on_expiry, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        ("RET-001", "ORG-001", "Default evidence retention", 365, "document,artifact,review", "archive", now, now),
                        ("RET-002", "ORG-002", "Customer A evidence retention", 730, "document,artifact,review", "archive", now, now),
                        ("RET-003", "ORG-003", "Customer B evidence retention", 180, "document,artifact,review", "redact", now, now),
                    ],
                )
            if connection.execute("SELECT COUNT(*) AS count FROM redaction_rules").fetchone()["count"] == 0:
                connection.executemany(
                    """
                    INSERT INTO redaction_rules (
                        redaction_policy_id, org_id, label, pii_fields_json, masking_strategy, applies_to, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        ("RED-001", "ORG-001", "Default PII masking", serialize_json(["email", "phone", "address"]), "partial-mask", "document,artifact", now, now),
                        ("RED-002", "ORG-002", "Customer A strict masking", serialize_json(["email", "phone", "address", "contract_id"]), "full-mask", "document,artifact", now, now),
                        ("RED-003", "ORG-003", "Customer B light masking", serialize_json(["email", "phone"]), "partial-mask", "document,artifact", now, now),
                    ],
                )

    def register_source(
        self,
        *,
        org_id: str,
        source_type: str,
        source_family: str,
        display_name: str,
        connector_name: str,
        parser_name: str,
        parser_version: str,
        trust_score: float = 0.72,
        pii_risk_level: str = "low",
        retention_policy_id: str | None = None,
        redaction_policy_id: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        source_id = f"SRC-{uuid4().hex[:10].upper()}"
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO source_registry (
                    source_id, org_id, source_type, source_family, display_name, connector_name,
                    parser_name, parser_version, retention_policy_id, redaction_policy_id, trust_score,
                    pii_risk_level, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    org_id,
                    source_type,
                    source_family,
                    display_name,
                    connector_name,
                    parser_name,
                    parser_version,
                    retention_policy_id or self.default_retention_policy_id(org_id),
                    redaction_policy_id or self.default_redaction_policy_id(org_id),
                    trust_score,
                    pii_risk_level,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO trust_scores (trust_score_id, org_id, source_id, score, rationale, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"TRS-{uuid4().hex[:10].upper()}",
                    org_id,
                    source_id,
                    trust_score,
                    f"Initialized from {connector_name} / {source_family}.",
                    now,
                ),
            )
        return self.source_detail(source_id, org_id)

    def source_detail(self, source_id: str, org_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            source = connection.execute(
                "SELECT * FROM source_registry WHERE source_id=? AND org_id=?",
                (source_id, org_id),
            ).fetchone()
            trust = connection.execute(
                "SELECT * FROM trust_scores WHERE source_id=? AND org_id=? ORDER BY updated_at DESC LIMIT 1",
                (source_id, org_id),
            ).fetchone()
        if not source:
            raise ValueError("Unknown source.")
        payload = dict(source)
        payload["latest_trust_score"] = dict(trust) if trust else None
        payload["retention"] = self.retention_rule(payload.get("retention_policy_id"), org_id)
        payload["redaction"] = self.redaction_rule(payload.get("redaction_policy_id"), org_id)
        return payload

    def list_sources(self, org_id: str) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM source_registry WHERE org_id=? ORDER BY updated_at DESC",
                (org_id,),
            ).fetchall()
        return [self.source_detail(row["source_id"], org_id) for row in rows]

    def retention_rule(self, retention_policy_id: str | None, org_id: str) -> dict[str, Any] | None:
        if not retention_policy_id:
            return None
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM retention_rules WHERE retention_policy_id=? AND org_id=?",
                (retention_policy_id, org_id),
            ).fetchone()
        return dict(row) if row else None

    def redaction_rule(self, redaction_policy_id: str | None, org_id: str) -> dict[str, Any] | None:
        if not redaction_policy_id:
            return None
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM redaction_rules WHERE redaction_policy_id=? AND org_id=?",
                (redaction_policy_id, org_id),
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["pii_fields"] = deserialize_json(payload["pii_fields_json"], [])
        return payload

    def default_retention_policy_id(self, org_id: str) -> str | None:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT retention_policy_id FROM retention_rules WHERE org_id=? ORDER BY created_at ASC LIMIT 1",
                (org_id,),
            ).fetchone()
        return row["retention_policy_id"] if row else None

    def default_redaction_policy_id(self, org_id: str) -> str | None:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT redaction_policy_id FROM redaction_rules WHERE org_id=? ORDER BY created_at ASC LIMIT 1",
                (org_id,),
            ).fetchone()
        return row["redaction_policy_id"] if row else None

    def apply_redaction(self, text: str, pii_flags: list[str], org_id: str) -> str:
        policy = self.redaction_rule(self.default_redaction_policy_id(org_id), org_id)
        if not policy or not pii_flags:
            return text
        masked = text
        for flag in pii_flags:
            masked = masked.replace(flag, "[redacted]")
        return masked

    def retention_preview(self, org_id: str, uploaded_at: str) -> dict[str, Any]:
        policy = self.retention_rule(self.default_retention_policy_id(org_id), org_id)
        if not policy:
            return {"status": "no_policy"}
        uploaded_at_dt = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00"))
        expires_at = uploaded_at_dt + timedelta(days=int(policy["retention_days"]))
        return {
            "policy_id": policy["retention_policy_id"],
            "label": policy["label"],
            "action_on_expiry": policy["action_on_expiry"],
            "expires_at": expires_at.isoformat(),
        }
