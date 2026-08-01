from __future__ import annotations

from datetime import datetime, UTC
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.core.runtime_db import RuntimeDatabase, deserialize_json, serialize_json
from app.services.governance_service import GovernanceService


class LineageService:
    def __init__(self, settings: Settings, runtime_db: RuntimeDatabase, governance: GovernanceService):
        self.settings = settings
        self.db = runtime_db
        self.governance = governance

    def record_lineage(
        self,
        *,
        org_id: str,
        source_id: str,
        artifact_id: str,
        entity_type: str,
        entity_id: str,
        field_name: str | None,
        citation_span: str | None,
        field_confidence: float | None,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        edge_id = f"LIN-{uuid4().hex[:10].upper()}"
        now = datetime.now(UTC).isoformat()
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO lineage_edges (
                    lineage_edge_id, org_id, source_id, artifact_id, entity_type, entity_id,
                    field_name, citation_span, field_confidence, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edge_id,
                    org_id,
                    source_id,
                    artifact_id,
                    entity_type,
                    entity_id,
                    field_name,
                    citation_span,
                    field_confidence,
                    serialize_json(metadata),
                    now,
                ),
            )
        return self.get_edge(edge_id, org_id)

    def get_edge(self, lineage_edge_id: str, org_id: str) -> dict[str, Any]:
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM lineage_edges WHERE lineage_edge_id=? AND org_id=?",
                (lineage_edge_id, org_id),
            ).fetchone()
        if not row:
            raise ValueError("Unknown lineage edge.")
        payload = dict(row)
        payload["metadata"] = deserialize_json(payload["metadata_json"], {})
        payload["source"] = self.governance.source_detail(payload["source_id"], org_id)
        return payload

    def list_for_entity(self, entity_type: str, entity_id: str, org_id: str) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM lineage_edges
                WHERE entity_type=? AND entity_id=? AND org_id=?
                ORDER BY created_at DESC
                """,
                (entity_type, entity_id, org_id),
            ).fetchall()
        return [self.get_edge(row["lineage_edge_id"], org_id) for row in rows]

    def provenance_viewer_payload(
        self,
        *,
        org_id: str,
        source_id: str,
        artifact_id: str,
        extracted_fields: list[dict[str, Any]],
        summary: str,
        uploaded_at: str,
    ) -> dict[str, Any]:
        source = self.governance.source_detail(source_id, org_id)
        retention = self.governance.retention_preview(org_id, uploaded_at)
        return {
            "source": {
                "source_id": source["source_id"],
                "display_name": source["display_name"],
                "connector_name": source["connector_name"],
                "source_family": source["source_family"],
                "trust_score": source["trust_score"],
                "pii_risk_level": source["pii_risk_level"],
            },
            "artifact": {
                "artifact_id": artifact_id,
                "summary": summary,
                "uploaded_at": uploaded_at,
            },
            "retention": retention,
            "extracted_fields": extracted_fields,
        }
