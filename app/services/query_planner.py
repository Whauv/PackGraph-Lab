from __future__ import annotations

import re
from typing import Any


class QueryPlanner:
    def plan(self, question: str, repository=None) -> dict[str, Any]:
        text = question.lower().strip()
        if len(text) < 8:
            return self._ambiguous(question, "Question is too short to safely route.")

        extracted = self._extract_entities(question, repository) if repository else {}
        rules: list[tuple[str, str, str, list[str]]] = [
            ("material_lookup", r"(tell me about|show me|details on|what is)\b", "Summarize a material from the demo graph", ["material_id"]),
            ("compare_materials", r"(compare materials|compare|versus| vs )", "Compare named materials with weighted demo attributes", ["material_ids"]),
            ("find_recyclable_substitutes", r"(substitute|replacement|alternative|swap)", "Find recyclable substitutes for a selected material", ["material_id"]),
            ("evidence_for_material", r"(evidence|provenance|document|datasheet|lab report|declaration)", "Trace evidence documents for a material", ["material_id"]),
            ("compare_suppliers", r"(compare suppliers|supplier comparison|supplier|esg|lead time|risk)", "Compare suppliers by ESG, risk, and lead time", ["supplier_ids"]),
            ("supplier_risk_ranking", r"(riskiest suppliers|highest supplier risk|supplier risk)", "Rank suppliers by disruption exposure", []),
            ("non_compliant_materials", r"(non.?compliant|regulation|violat|out of bounds|affected)", "Identify materials that fail a selected regulation screen", ["regulation_id"]),
            ("materials_at_risk", r"(materials at risk|disruption|unavailable supplier|risk exposure)", "Find materials exposed to supplier disruption", []),
            ("material_filter", r"(show|list|find|which).*(materials|films|bioplastics|coatings|paper|laminates)", "Filter the material portfolio using natural language constraints", []),
            ("recommend_food_packaging", r"(recommend|best|food packaging|snack|pouch|food-safe|compostable|recyclable)", "Recommend food-safe packaging materials", []),
        ]
        for intent, pattern, explanation, params in rules:
            if re.search(pattern, text):
                return {
                    "intent": intent,
                    "cypher_template": intent.upper(),
                    "parameters_needed": params,
                    "explanation": explanation,
                    "entities": extracted,
                    "audit": {
                        "reviewed_template": True,
                        "ambiguity": any(param.endswith("_id") and not extracted.get(param) and not extracted.get(param.replace("_id", "_ids")) for param in params),
                        "fallback_used": False,
                    },
                }
        return self._ambiguous(question, "No reviewed intent matched the request.")

    def _extract_entities(self, question: str, repository) -> dict[str, Any]:
        text = question.lower()
        materials = []
        suppliers = []
        regulations = []
        applications = []

        for item in repository.materials:
            if item["name"].lower() in text:
                materials.append(item["material_id"])
        for item in repository.suppliers:
            if item["name"].lower() in text:
                suppliers.append(item["supplier_id"])
        for item in repository.regulations:
            if item["name"].lower() in text:
                regulations.append(item["regulation_id"])
        for item in repository.applications:
            if item["name"].lower() in text:
                applications.append(item["application_id"])

        region = next((item["name"] for item in repository.regions if item["name"].lower() in text), None)
        category_map = {
            "film": "film",
            "bioplastic": "bioplastic",
            "coating": "coating",
            "laminate": "laminate",
            "paper composite": "paper composite",
            "adhesive": "adhesive",
        }
        category = next((value for key, value in category_map.items() if key in text), None)
        compliance_state = None
        if "non-compliant" in text or "non compliant" in text:
            compliance_state = "non-compliant"
        elif "compliant" in text:
            compliance_state = "compliant"
        elif "watch" in text or "under review" in text:
            compliance_state = "watch"

        min_sustainability = None
        sustainability_match = re.search(r"(?:sustainability|sustainable).*?(\d{2,3})", text)
        if sustainability_match:
            min_sustainability = int(sustainability_match.group(1))

        prioritize_sustainability = any(token in text for token in ["sustainable", "sustainability", "compostable", "recyclable", "lower footprint"])
        prioritize_cost = any(token in text for token in ["cheap", "cheapest", "low cost", "lower cost", "cost efficient"])
        food_safe = any(token in text for token in ["food safe", "food-safe", "food contact", "snack", "pouch", "packaging"])

        return {
            "material_id": materials[0] if materials else None,
            "material_ids": materials,
            "supplier_id": suppliers[0] if suppliers else None,
            "supplier_ids": suppliers,
            "regulation_id": regulations[0] if regulations else None,
            "application_id": applications[0] if applications else None,
            "region": region,
            "category": category,
            "compliance_state": compliance_state,
            "min_sustainability": min_sustainability,
            "prioritize_sustainability": prioritize_sustainability,
            "prioritize_cost": prioritize_cost,
            "food_safe": food_safe,
        }

    def _ambiguous(self, question: str, reason: str) -> dict[str, Any]:
        return {
            "intent": "refuse_or_clarify",
            "cypher_template": None,
            "parameters_needed": [],
            "entities": {},
            "explanation": "The request needs clarification before a reviewed query template can be selected.",
            "audit": {
                "reviewed_template": False,
                "ambiguity": True,
                "fallback_used": True,
                "reason": reason,
                "question": question,
            },
        }
