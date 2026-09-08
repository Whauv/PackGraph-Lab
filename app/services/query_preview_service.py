from __future__ import annotations

from typing import Any

from app.services.private_data_service import PrivateDataService
from app.services.query_context import QueryContextAdapter
from app.services.query_planner import QueryPlanner
from app.services.query_response_builder import QueryResponseBuilder
from app.services.source_intake_service import SourceIntakeService
from app.services.workflow_status_service import WorkflowStatusService


class QueryPreviewService:
    def __init__(
        self,
        *,
        repository,
        planner: QueryPlanner,
        context_adapter: QueryContextAdapter,
        response_builder: QueryResponseBuilder,
        workflow_status: WorkflowStatusService,
        private_data: PrivateDataService | None = None,
        source_intake: SourceIntakeService | None = None,
    ) -> None:
        self.repository = repository
        self.planner = planner
        self.context_adapter = context_adapter
        self.response_builder = response_builder
        self.workflow_status = workflow_status
        self.private_data = private_data
        self.source_intake = source_intake

    def preview(
        self,
        question: str,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        mode: str = "quick_ask",
    ) -> dict[str, Any]:
        resolved_question = self.context_adapter.merge_context_into_question(question, context)
        plan = self.planner.plan(resolved_question, self.repository, context)
        plan.setdefault("entities", {})["chat_mode"] = mode
        private_status = self.private_data.private_status() if self.private_data else {"private_data_active": False, "dataset_count": 0, "record_count": 0}
        private_lookup = self.private_data.query(resolved_question) if self.private_data and private_status["private_data_active"] else {"rows": []}
        source_lookup = self.source_intake.search(resolved_question) if self.source_intake else {"rows": []}
        route = "source_intake" if self._should_route_to_source_intake(resolved_question, source_lookup) else self.response_builder.route_question(plan, private_lookup)
        template = self.workflow_status.template_schema_status(plan["intent"])
        return {
            "route": route,
            "intent": plan["intent"],
            "template": plan.get("cypher_template") or "NO_REVIEWED_TEMPLATE",
            "schema_supported": template["schema_supported"],
            "blockers": template["blockers"],
            "mode": mode,
            "context": self._safe_context_preview(context),
            "requires_review": route in {"private_data", "source_intake"} or bool(template["blockers"]),
            "private_data_active": private_status["private_data_active"],
            "source_matches_found": len(source_lookup.get("rows", [])),
            "safe_metadata_only": True,
            "options_received": sorted((options or {}).keys())[:8],
        }

    def _should_route_to_source_intake(self, question: str, source_lookup: dict[str, Any]) -> bool:
        return bool(source_lookup.get("rows")) and self._source_intake_question(question)

    def _source_intake_question(self, question: str) -> bool:
        lowered = question.lower()
        return any(
            marker in lowered
            for marker in [
                "uploaded",
                "source",
                "json",
                "pdf",
                "file",
                "schema",
                "extracted",
                "document",
                "record",
                "component",
            ]
        )

    def _safe_context_preview(self, context: dict[str, Any] | None) -> dict[str, Any]:
        if not context:
            return {}
        metadata = context.get("metadata") or {}
        return {
            "entity_type": context.get("entity_type"),
            "entity_id": context.get("entity_id"),
            "entity_name": context.get("entity_name"),
            "metadata_keys": sorted(metadata.keys())[:8],
            "history_count": len(context.get("history") or []),
        }
