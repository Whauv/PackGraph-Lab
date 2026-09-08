from __future__ import annotations

from typing import Any

from app.services.query_enrichment_service import QueryEnrichmentService
from app.services.workflow_status_service import WorkflowStatusService


class QueryQualityService:
    def __init__(self, workflow_status: WorkflowStatusService, enrichment: QueryEnrichmentService) -> None:
        self.workflow_status = workflow_status
        self.enrichment = enrichment

    def build_package(
        self,
        *,
        intent: str,
        route: str,
        template_name: str,
        classifier: dict[str, Any],
        plan: dict[str, Any],
        context: dict[str, Any] | None,
        scored_rows: list[dict[str, Any]],
        evidence_rows: list[dict[str, Any]],
        review_candidate: dict[str, Any] | None,
        enrichment_request: dict[str, Any] | None,
        latency_ms: int,
    ) -> dict[str, Any]:
        schema_status = self.workflow_status.template_schema_status(intent)
        return {
            "route_preview": {
                "route": route,
                "intent": intent,
                "template": template_name,
                "schema_supported": schema_status["schema_supported"],
                "blockers": schema_status["blockers"],
                "context_entity": self.enrichment.context_label(context),
                "mode": (plan.get("entities", {}) or {}).get("chat_mode") or "quick_ask",
                "safe_metadata_only": True,
            },
            "answer_quality": self.answer_quality(scored_rows, evidence_rows, review_candidate, enrichment_request),
            "empty_state": self.empty_state(intent, route, enrichment_request) if not scored_rows else {},
            "provenance": {
                "verified_kg": [row for row in scored_rows if not self.is_provisional_row(row)],
                "provisional": [row for row in scored_rows if self.is_provisional_row(row)],
                "evidence_rows": evidence_rows,
            },
            "execution_metadata": {
                "template": template_name,
                "route": route,
                "intent": intent,
                "latency_ms": latency_ms,
                "provisional_writeback_enabled": False,
            },
        }

    def answer_quality(
        self,
        rows: list[dict[str, Any]],
        evidence_rows: list[dict[str, Any]],
        review_candidate: dict[str, Any] | None,
        enrichment_request: dict[str, Any] | None,
    ) -> dict[str, Any]:
        provisional = [row for row in rows if self.is_provisional_row(row)]
        verified = [row for row in rows if not self.is_provisional_row(row)]
        confidences = [self._confidence_value(row) for row in rows]
        unstamped = [
            row
            for row in rows
            if not (row.get("provenance_id") or row.get("source_id") or row.get("edge_key") or row.get("entity_id") or row.get("material_id") or row.get("supplier_id"))
        ]
        return {
            "status": "no_verified_rows" if not verified else "answered",
            "row_count": len(rows),
            "has_provisional_data": bool(provisional),
            "verified_count": len(verified),
            "provisional_count": len(provisional),
            "lowest_confidence": round(min(confidences), 2) if confidences else 0.0,
            "needs_validation": bool(provisional or review_candidate or enrichment_request or unstamped),
            "lineage_checked": bool(evidence_rows) or all(row.get("entity_id") or row.get("provenance_id") or row.get("edge_key") for row in rows),
            "unstamped_result_count": len(unstamped),
        }

    def empty_state(self, intent: str, route: str, enrichment_request: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "title": "No verified graph rows found",
            "message": "The query ran, but PackGraph could not find a verified relationship for this request.",
            "no_result_cause": self.no_result_cause(intent, route),
            "intent": intent,
            "route": route,
            "next_action": "Review the staged enrichment request before adding anything to the graph." if enrichment_request else "Try a narrower material, supplier, or evidence question.",
        }

    def no_result_cause(self, intent: str, route: str) -> str:
        if route == "source_intake":
            return "raw_uploaded_record"
        if intent in {"selected_supplier_lookup", "selected_material_lookup", "uploaded_record_lookup"}:
            return "wrong_entity_type"
        if not self.workflow_status.template_schema_status(intent)["schema_supported"]:
            return "schema_mismatch"
        if intent in {"suppliers_for_material", "evidence_for_material", "find_recyclable_substitutes"}:
            return "missing_modeled_relationship"
        return "no_rows_for_template"

    def is_provisional_row(self, row: dict[str, Any]) -> bool:
        return (
            row.get("source_type") == "llm_inferred"
            or row.get("assertion_kind") == "LLM_INFERRED"
            or row.get("validation_status") == "pending"
        )

    def _confidence_value(self, row: dict[str, Any]) -> float:
        try:
            raw = float(row.get("confidence", row.get("score", 0)) or 0)
        except (TypeError, ValueError):
            raw = 0.0
        return raw / 100 if raw > 1 else raw
