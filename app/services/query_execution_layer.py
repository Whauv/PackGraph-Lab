from __future__ import annotations

from typing import Any


class QueryExecutionLayer:
    def __init__(self, repository, formatter) -> None:
        self.repository = repository
        self.formatter = formatter

    def recommend_materials(self, entities: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = self.repository.recommend_food_packaging(entities.get("prioritize_sustainability", False))
        region = entities.get("region")
        category = entities.get("category")
        if region or category:
            filtered = []
            for candidate in candidates:
                material = self.repository.material_index.get(candidate["material_id"])
                if not material:
                    continue
                if region and region not in material["regions_available"]:
                    continue
                if category and material["category"] != category:
                    continue
                filtered.append(candidate)
            candidates = filtered
        if entities.get("prioritize_cost"):
            candidates = sorted(candidates, key=lambda item: self.repository.material_index[item["material_id"]]["cost_range"]["high"])
        return candidates[:6]

    def filter_materials_from_question(self, entities: dict[str, Any]) -> list[dict[str, Any]]:
        materials = self.repository.filter_materials(
            region=entities.get("region"),
            category=entities.get("category"),
            compliance_state=entities.get("compliance_state"),
            min_sustainability=entities.get("min_sustainability"),
        )
        if entities.get("food_safe"):
            materials = [item for item in materials if item["food_contact_safe"]]
        if entities.get("application_id"):
            materials = [item for item in materials if entities["application_id"] in item["target_applications"]]
        if entities.get("supplier_id"):
            materials = [item for item in materials if entities["supplier_id"] in item["supplier_ids"]]
        if entities.get("prioritize_cost"):
            materials = sorted(materials, key=lambda item: item["cost_range"]["high"])
        elif entities.get("prioritize_sustainability"):
            materials = sorted(materials, key=lambda item: item["sustainability_score"], reverse=True)
        return materials

    def execute(self, question: str, intent: str, entities: dict[str, Any], private_lookup: dict[str, Any]) -> tuple[Any, str, str]:
        source = "graph"
        result = None
        message = ""
        if intent == "recommend_food_packaging":
            result = self.recommend_materials(entities)
            message = self.formatter.summarize_material_list(result, "Recommended materials from the synthetic packaging graph")
        elif intent == "selected_material_lookup":
            material_id = entities.get("material_id") or entities.get("selected_entity_id")
            result = self.repository.selected_material_lookup(material_id) if material_id else None
            message = self.formatter.summarize_selected_material_lookup(result, material_id)
        elif intent == "selected_supplier_lookup":
            supplier_id = entities.get("supplier_id") or entities.get("selected_entity_id")
            result = self.repository.selected_supplier_lookup(supplier_id) if supplier_id else None
            message = self.formatter.summarize_selected_supplier_lookup(result, supplier_id)
        elif intent == "selected_entity_lookup":
            result = self.repository.selected_entity_lookup(
                entities.get("selected_entity_type"),
                entities.get("selected_entity_id"),
                entities.get("selected_entity_name") or entities.get("context_name"),
            )
            message = self.formatter.summarize_selected_entity_lookup(result)
        elif intent == "uploaded_record_lookup":
            result = self.repository.uploaded_record_lookup(
                entities.get("selected_entity_type"),
                entities.get("record_id") or entities.get("selected_entity_id"),
                entities.get("selected_entity_name") or entities.get("context_name"),
            )
            message = self.formatter.summarize_uploaded_record_lookup(result)
        elif intent == "suppliers_for_material":
            material_id = entities.get("material_id") or "MAT-001"
            material = self.repository.get_material(material_id)
            suppliers = material.get("suppliers", []) if material else []
            result = self.repository.compare_suppliers([item["supplier_id"] for item in suppliers]) if suppliers else []
            label = material["name"] if material else material_id
            message = self.formatter.summarize_supplier_list(result[:5], f"Qualified suppliers for {label}")
        elif intent == "find_recyclable_substitutes":
            material_id = entities.get("material_id") or entities.get("focus_material_id") or "MAT-001"
            result = self.repository.find_recyclable_substitutes(material_id)
            base = self.repository.get_material(material_id)
            label = base["name"] if base else material_id
            message = self.formatter.summarize_material_list(result, f"Recyclable substitutes for {label}")
        elif intent == "compare_suppliers":
            supplier_ids = entities.get("supplier_ids") or ([entities["supplier_id"]] if entities.get("supplier_id") else None)
            result = self.repository.compare_suppliers(supplier_ids)
            message = self.formatter.summarize_supplier_list(result[:4], "Supplier comparison across ESG, risk, and lead time")
        elif intent == "supplier_risk_ranking":
            result = sorted(self.repository.compare_suppliers(), key=lambda item: item["disruption_risk_score"], reverse=True)[:5]
            message = self.formatter.summarize_supplier_list(result, "Highest-risk suppliers in the demo portfolio")
        elif intent == "non_compliant_materials":
            regulation_id = entities.get("regulation_id") or "REGU-003"
            result = self.repository.non_compliant_materials(regulation_id)
            regulation = self.repository.regulation_index.get(regulation_id)
            label = regulation["name"] if regulation else regulation_id
            message = self.formatter.summarize_material_list(result, f"Materials currently failing or at risk under {label}")
        elif intent == "evidence_for_material":
            material_id = entities.get("material_id") or "MAT-001"
            result = self.repository.evidence_for_material(material_id)
            message = self.formatter.summarize_evidence(result)
        elif intent == "materials_at_risk":
            result = self.repository.materials_at_risk()
            message = self.formatter.summarize_risk_materials(result[:5])
        elif intent == "material_lookup":
            material_id = entities.get("material_id") or "MAT-001"
            result = self.repository.get_material(material_id)
            message = self.formatter.summarize_material_detail(result)
        elif intent == "material_filter":
            result = self.filter_materials_from_question(entities)
            message = self.formatter.summarize_material_list(result[:6], "Filtered materials matching your natural-language constraints")
        elif intent == "compare_materials":
            material_ids = entities.get("material_ids") or ([entities["material_id"]] if entities.get("material_id") else [])
            result = self.repository.compare_materials(material_ids[:4]) if material_ids else []
            message = self.formatter.summarize_comparison(result)
        elif intent == "catalog_lookup" and private_lookup["rows"]:
            source = "private_data"
            result = {"rows": private_lookup["rows"], "private_query": private_lookup.get("query", {})}
            top_rows = private_lookup["rows"][:6]
            if top_rows:
                message = "Private data lookup returned the strongest matching records for this question:\n" + "\n".join(
                    f"{item['label']} | {item['entity_type']} | score {item['score']}" for item in top_rows
                )
            else:
                message = "Private data is active, but no matching private records were found for the current question."
        return result, message, source
