from __future__ import annotations

import re
from typing import Any


class QueryPlanner:
    def plan(self, question: str) -> dict[str, Any]:
        text = question.lower().strip()
        if len(text) < 8:
            return self._ambiguous(question, "Question is too short to safely route.")
        rules: list[tuple[str, str, str, list[str]]] = [
            ("recommend_food_packaging", r"(recommend|best|food packaging|snack|pouch)", "Recommend food-safe packaging materials", ["application", "priority"]),
            ("find_recyclable_substitutes", r"(substitute|replacement|alternative)", "Find recyclable substitutes for a selected material", ["material_id"]),
            ("compare_suppliers", r"(compare suppliers|supplier comparison|esg|lead time|risk)", "Compare suppliers by ESG, risk, and lead time", ["supplier_ids"]),
            ("non_compliant_materials", r"(non.?compliant|regulation|violat)", "Identify materials that fail a selected regulation screen", ["regulation_id"]),
            ("evidence_for_material", r"(evidence|provenance|document|datasheet|lab report)", "Trace evidence documents for a material", ["material_id"]),
            ("materials_at_risk", r"(risk|disruption|unavailable supplier)", "Find materials exposed to supplier disruption", []),
        ]
        for intent, pattern, explanation, params in rules:
            if re.search(pattern, text):
                return {
                    "intent": intent,
                    "cypher_template": intent.upper(),
                    "parameters_needed": params,
                    "explanation": explanation,
                    "audit": {
                        "reviewed_template": True,
                        "ambiguity": len(params) > 0,
                        "fallback_used": False,
                    },
                }
        return self._ambiguous(question, "No reviewed intent matched the request.")

    def _ambiguous(self, question: str, reason: str) -> dict[str, Any]:
        return {
            "intent": "refuse_or_clarify",
            "cypher_template": None,
            "parameters_needed": [],
            "explanation": "The request needs clarification before a reviewed query template can be selected.",
            "audit": {
                "reviewed_template": False,
                "ambiguity": True,
                "fallback_used": True,
                "reason": reason,
                "question": question,
            },
        }
