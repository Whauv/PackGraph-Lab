from __future__ import annotations

from typing import Any


class InvestigationPlanner:
    def build_plan(self, question: str, intent: str, entities: dict[str, Any]) -> dict[str, Any]:
        steps = ["resolve_intent_and_entities"]
        if entities.get("material_id") or entities.get("material_ids"):
            steps.append("find_source_entity")
        if intent == "find_recyclable_substitutes":
            steps.extend(
                [
                    "find_substitutes",
                    "filter_application_fit",
                    "check_supplier_risk",
                    "retrieve_evidence",
                    "rank_answer",
                    "review_before_writeback",
                ]
            )
        elif intent in {"compare_suppliers", "supplier_risk_ranking"}:
            steps.extend(["load_supplier_set", "score_supplier_risk", "retrieve_evidence", "rank_answer"])
        elif intent in {"evidence_for_material", "catalog_lookup"}:
            steps.extend(["retrieve_evidence", "score_evidence_strength", "review_before_writeback"])
        else:
            steps.extend(["query_reviewed_template", "rank_answer"])
        return {
            "question": question,
            "intent": intent,
            "steps": steps,
        }
