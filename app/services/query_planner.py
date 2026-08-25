from __future__ import annotations

import re
from typing import Any


class QueryPlanner:
    def plan(self, question: str, repository=None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        text = question.lower().strip()
        if len(text) < 8:
            return self._ambiguous(question, "Question is too short to safely route.")

        extracted = self._extract_entities(question, repository, context) if repository else {}
        selected_plan = self._plan_from_selected_context(question, text, extracted, context, repository)
        if selected_plan:
            return selected_plan
        rules: list[tuple[str, str, str, list[str]]] = [
            ("suppliers_for_material", r"(show|list|find|which|who).*(suppliers?|sources?).*(for|of|used by|qualified|this|that|it)", "List qualified suppliers for a selected material", ["material_id"]),
            ("material_lookup", r"(tell me about|show me|details on|what is)\b", "Summarize a material from the demo graph", ["material_id"]),
            ("compare_materials", r"(compare materials|compare|versus| vs )", "Compare named materials with weighted demo attributes", ["material_ids"]),
            ("find_recyclable_substitutes", r"(substitute|replacement|alternative|swap)", "Find recyclable substitutes for a selected material", ["material_id"]),
            ("evidence_for_material", r"(evidence|provenance|document|datasheet|lab report|declaration)", "Trace evidence documents for a material", ["material_id"]),
            ("compare_suppliers", r"(compare suppliers|supplier comparison|supplier|esg|lead time|risk)", "Compare suppliers by ESG, risk, and lead time", ["supplier_ids"]),
            ("supplier_risk_ranking", r"(riskiest suppliers|highest supplier risk|supplier risk)", "Rank suppliers by disruption exposure", []),
            ("non_compliant_materials", r"(non.?compliant|regulation|violat|out of bounds|affected)", "Identify materials that fail a selected regulation screen", ["regulation_id"]),
            ("materials_at_risk", r"(materials at risk|disruption|unavailable supplier|risk exposure)", "Find materials exposed to supplier disruption", []),
            ("catalog_lookup", r"(find|list|search|lookup|show).*(products?|suppliers?|materials?|locations?|grades?)", "Search product, supplier, material, location, or grade records", []),
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

    def _extract_entities(self, question: str, repository, context: dict[str, Any] | None = None) -> dict[str, Any]:
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
        location_hint_match = re.search(r"\bin\s+([a-z][a-z\s\-]+?)(?:\?|$| with | for | that | where )", text)
        location_hint = location_hint_match.group(1).strip() if location_hint_match else None
        entity_target = next((term.rstrip("s") for term in ["products", "suppliers", "materials", "locations", "grades"] if term in text), None)
        search_keywords = [
            token for token in re.findall(r"[a-z0-9][a-z0-9\-/]+", text)
            if token not in {"a", "an", "and", "best", "by", "find", "for", "from", "in", "list", "lookup", "search", "show", "the", "what", "which"}
            and token not in {"products", "suppliers", "materials", "locations", "grades"}
            and token != (location_hint or "")
        ]

        entities = {
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
            "location_hint": location_hint,
            "entity_target": entity_target,
            "search_keywords": search_keywords[:8],
        }
        if context:
            if context.get("entity_id"):
                entities["selected_entity_id"] = context.get("entity_id")
            if context.get("entity_name"):
                entities["selected_entity_name"] = context.get("entity_name")
            if context.get("entity_type"):
                entities["selected_entity_type"] = str(context.get("entity_type")).lower()
            history = context.get("history") or []
            if history:
                entities["selected_context_history"] = history[:4]
        return entities

    def _plan_from_selected_context(
        self,
        question: str,
        text: str,
        entities: dict[str, Any],
        context: dict[str, Any] | None,
        repository,
    ) -> dict[str, Any] | None:
        if not context:
            return None
        entity_type = str(context.get("entity_type") or "").lower()
        entity_id = context.get("entity_id")
        entity_name = context.get("entity_name")
        history = context.get("history") or []
        compare_requested = "compare selected" in text or "compare these" in text or "compare this to" in text
        if compare_requested and history:
            material_ids = [item.get("entity_id") for item in [context, *history] if str(item.get("entity_type") or "").lower() == "material" and item.get("entity_id")]
            if len(material_ids) >= 2:
                entities["material_ids"] = list(dict.fromkeys(material_ids[:4]))
                return self._selected_template(
                    "compare_materials",
                    "COMPARE_MATERIALS",
                    "Compare the selected materials from active chat context.",
                    ["material_ids"],
                    entities,
                )

        if entity_type in {"document", "report", "test_report", "component", "source", "source_document", "uploaded_record"}:
            entities["record_id"] = entity_id
            return self._selected_template(
                "uploaded_record_lookup",
                "UPLOADED_RECORD_LOOKUP",
                "Inspect the selected uploaded or source-backed record.",
                ["record_id"],
                entities,
            )

        if entity_type == "supplier":
            entities["supplier_id"] = entity_id
            entities["supplier_ids"] = [entity_id] if entity_id else []
            if any(token in text for token in ["material", "supplied", "supplies"]):
                return self._selected_template(
                    "selected_supplier_lookup",
                    "SELECTED_SUPPLIER_LOOKUP",
                    "Inspect the selected supplier directly from graph context.",
                    ["supplier_id"],
                    entities,
                )
            if not any(token in text for token in ["rank", "ranking", "top suppliers", "compare suppliers"]):
                return self._selected_template(
                    "selected_supplier_lookup",
                    "SELECTED_SUPPLIER_LOOKUP",
                    "Inspect the selected supplier directly from graph context.",
                    ["supplier_id"],
                    entities,
                )

        if entity_type == "material":
            entities["material_id"] = entity_id
            if any(token in text for token in ["supplier", "source", "qualified"]):
                return self._selected_template(
                    "suppliers_for_material",
                    "SUPPLIERS_FOR_MATERIAL",
                    "List qualified suppliers for the selected material.",
                    ["material_id"],
                    entities,
                )
            if any(token in text for token in ["evidence", "proof", "source", "document", "datasheet", "lab report", "declaration"]):
                return self._selected_template(
                    "evidence_for_material",
                    "EVIDENCE_FOR_MATERIAL",
                    "Trace evidence documents for the selected material.",
                    ["material_id"],
                    entities,
                )
            if any(token in text for token in ["substitute", "alternative", "replacement"]):
                return self._selected_template(
                    "find_recyclable_substitutes",
                    "FIND_RECYCLABLE_SUBSTITUTES",
                    "Find substitutes for the selected material.",
                    ["material_id"],
                    entities,
                )
            return self._selected_template(
                "selected_material_lookup",
                "SELECTED_MATERIAL_LOOKUP",
                "Inspect the selected material directly from graph context.",
                ["material_id"],
                entities,
            )

        if entity_id or entity_name:
            resolved = repository.selected_entity_lookup(entity_type or None, entity_id, entity_name) if repository else None
            if resolved:
                resolved_entity = resolved["entity"]
                entities["selected_entity_type"] = resolved_entity["type"]
                entities["selected_entity_id"] = resolved_entity["id"]
            return self._selected_template(
                "selected_entity_lookup",
                "SELECTED_ENTITY_LOOKUP",
                "Resolve the selected entity against likely graph labels before fallback.",
                ["selected_entity_id"],
                entities,
            )
        return None

    def _selected_template(
        self,
        intent: str,
        template_name: str,
        explanation: str,
        parameters_needed: list[str],
        entities: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "intent": intent,
            "cypher_template": template_name,
            "parameters_needed": parameters_needed,
            "explanation": explanation,
            "entities": entities,
            "audit": {
                "reviewed_template": True,
                "ambiguity": False,
                "fallback_used": False,
            },
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
