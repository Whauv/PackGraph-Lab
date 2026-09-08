from __future__ import annotations

import hashlib
import re
from typing import Any


class QueryEnrichmentService:
    def __init__(self, agent_tools) -> None:
        self.agent_tools = agent_tools

    def enrich(self, question: str, options: dict[str, Any], context: dict[str, Any] | None, plan: dict[str, Any]) -> dict[str, Any]:
        request = self.build_request(question, plan, context, [])
        review_tool = self.agent_tools.create_review_candidate(
            "graph_enrichment_request",
            "Potential graph data gap should be reviewed before any KG write-back.",
            {"enrichment_request": request, "options": options},
        )
        return {
            "status": "staged_for_review",
            "enrichment_request": request,
            "review_candidate": review_tool["output"],
            "writeback_allowed": False,
        }

    def build_request(
        self,
        query: str,
        plan: dict[str, Any],
        context: dict[str, Any] | None,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if rows:
            return None
        source = self.context_label(context) or plan.get("entities", {}).get("material_id") or "unknown_source"
        target = self._target_from_question(query)
        relationship = self._relationship_for_intent(plan.get("intent", "unknown"))
        edge_key_raw = f"{source}|{relationship}|{target}|{query}".lower()
        return {
            "source": source,
            "relationship": relationship,
            "target": target,
            "confidence": 0.36,
            "evidence": [],
            "query": query,
            "model": "packgraph-local-enrichment-stub",
            "edge_key": hashlib.sha256(edge_key_raw.encode("utf-8")).hexdigest()[:16],
            "source_type": "llm_inferred",
            "assertion_kind": "LLM_INFERRED",
            "validation_status": "pending",
            "verification_status": "unverified",
            "promotion_status": "not_promoted",
        }

    def context_label(self, context: dict[str, Any] | None) -> str:
        if not context:
            return ""
        return context.get("entity_id") or context.get("entity_name") or context.get("entity_type") or ""

    def _relationship_for_intent(self, intent: str) -> str:
        mapping = {
            "suppliers_for_material": "SUPPLIED_BY",
            "evidence_for_material": "HAS_DOCUMENT",
            "find_recyclable_substitutes": "SUBSTITUTES_WITH",
            "compare_materials": "COMPARES_WITH",
            "selected_supplier_lookup": "SUPPLIES",
            "selected_material_lookup": "RELATED_TO",
        }
        return mapping.get(intent, "NEEDS_REVIEW_RELATIONSHIP")

    def _target_from_question(self, query: str) -> str:
        tokens = [
            token
            for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", query)
            if token.lower() not in {"show", "what", "where", "with", "this", "that", "about", "source"}
        ]
        return " ".join(tokens[-4:]) or "unknown_target"
