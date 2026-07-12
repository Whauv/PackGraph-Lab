from __future__ import annotations

from typing import Any

from app.repositories.graph_repository import LocalGraphRepository
from app.services.query_planner import QueryPlanner
from app.services.scenario_engine import ScenarioEngine


class QueryEngine:
    def __init__(self, repository: LocalGraphRepository):
        self.repository = repository
        self.planner = QueryPlanner()
        self.scenarios = ScenarioEngine(repository)

    def ask(self, question: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        plan = self.planner.plan(question, self.repository)
        intent = plan["intent"]
        if intent == "refuse_or_clarify":
            return {"plan": plan, "result": None, "message": plan["audit"]["reason"]}

        entities = {**plan.get("entities", {}), **options}
        result = None
        message = plan["explanation"]
        if intent == "recommend_food_packaging":
            result = self._recommend_materials(question, entities)
            message = self._summarize_material_list(result, "Recommended materials from the synthetic packaging graph")
        elif intent == "find_recyclable_substitutes":
            material_id = entities.get("material_id") or entities.get("focus_material_id") or "MAT-001"
            result = self.repository.find_recyclable_substitutes(material_id)
            base = self.repository.get_material(material_id)
            label = base["name"] if base else material_id
            message = self._summarize_material_list(result, f"Recyclable substitutes for {label}")
        elif intent == "compare_suppliers":
            supplier_ids = entities.get("supplier_ids") or ([entities["supplier_id"]] if entities.get("supplier_id") else None)
            result = self.repository.compare_suppliers(supplier_ids)
            message = self._summarize_supplier_list(result[:4], "Supplier comparison across ESG, risk, and lead time")
        elif intent == "supplier_risk_ranking":
            result = sorted(self.repository.compare_suppliers(), key=lambda item: item["disruption_risk_score"], reverse=True)[:5]
            message = self._summarize_supplier_list(result, "Highest-risk suppliers in the demo portfolio")
        elif intent == "non_compliant_materials":
            regulation_id = entities.get("regulation_id") or "REGU-003"
            result = self.repository.non_compliant_materials(regulation_id)
            regulation = self.repository.regulation_index.get(regulation_id)
            label = regulation["name"] if regulation else regulation_id
            message = self._summarize_material_list(result, f"Materials currently failing or at risk under {label}")
        elif intent == "evidence_for_material":
            material_id = entities.get("material_id") or "MAT-001"
            result = self.repository.evidence_for_material(material_id)
            message = self._summarize_evidence(result)
        elif intent == "materials_at_risk":
            result = self.repository.materials_at_risk()
            message = self._summarize_risk_materials(result[:5])
        elif intent == "material_lookup":
            material_id = entities.get("material_id") or "MAT-001"
            result = self.repository.get_material(material_id)
            message = self._summarize_material_detail(result)
        elif intent == "material_filter":
            result = self._filter_materials_from_question(entities)
            message = self._summarize_material_list(result[:6], "Filtered materials matching your natural-language constraints")
        elif intent == "compare_materials":
            material_ids = entities.get("material_ids") or ([entities["material_id"]] if entities.get("material_id") else [])
            result = self.repository.compare_materials(material_ids[:4]) if material_ids else []
            message = self._summarize_comparison(result)

        if result is None:
            result = self.repository.materials_at_risk()

        return {
            "plan": plan,
            "result": result,
            "message": message,
        }

    def run_scenario(self, scenario: str, material_id: str | None = None, supplier_id: str | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.scenarios.run(scenario=scenario, material_id=material_id, supplier_id=supplier_id, options=options)

    def _recommend_materials(self, question: str, entities: dict[str, Any]) -> list[dict[str, Any]]:
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

    def _filter_materials_from_question(self, entities: dict[str, Any]) -> list[dict[str, Any]]:
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

    def _summarize_material_list(self, materials: list[dict[str, Any]], intro: str) -> str:
        if not materials:
            return f"{intro}: no matching materials were found in the current synthetic dataset."
        lines = []
        for item in materials[:4]:
            if "material_id" in item and item["material_id"] in self.repository.material_index:
                material = self.repository.material_index[item["material_id"]]
                lines.append(
                    f"{material['name']} ({material['category']}) | sustainability {material['sustainability_score']} | "
                    f"recyclability {material['recyclability_score']} | compliance {material['compliance_state']}"
                )
            else:
                lines.append(str(item))
        return f"{intro}:\n" + "\n".join(lines)

    def _summarize_supplier_list(self, suppliers: list[dict[str, Any]], intro: str) -> str:
        if not suppliers:
            return f"{intro}: no matching suppliers were found."
        return f"{intro}:\n" + "\n".join(
            f"{item['name']} | risk {item['disruption_risk_score']} | ESG {item['esg_score']} | lead time {item['lead_time_days']} days"
            for item in suppliers[:4]
        )

    def _summarize_risk_materials(self, materials: list[dict[str, Any]]) -> str:
        if not materials:
            return "No high-risk materials were found in the current dataset."
        return "Most exposed materials in the current synthetic graph:\n" + "\n".join(
            f"{item['name']} | average supplier risk {item['supplier_risk_score']}" for item in materials
        )

    def _summarize_evidence(self, payload: dict[str, Any]) -> str:
        if not payload or not payload.get("material"):
            return "No evidence bundle was found for that material."
        material = payload["material"]
        documents = payload.get("documents", [])
        reports = payload.get("test_reports", [])
        return (
            f"Evidence for {material['name']}: {len(documents)} source documents and {len(reports)} test reports.\n"
            + "\n".join(f"{item['title']}" for item in documents[:3] + reports[:2])
        )

    def _summarize_material_detail(self, material: dict[str, Any] | None) -> str:
        if not material:
            return "That material could not be found in the demo graph."
        return (
            f"{material['name']} is a {material['category']} material made from {material['composition']}.\n"
            f"Sustainability {material['sustainability_score']}, recyclability {material['recyclability_score']}, "
            f"compliance {material['compliance_state']}, suppliers {len(material['suppliers'])}."
        )

    def _summarize_comparison(self, results: list[dict[str, Any]]) -> str:
        if not results:
            return "I could not compare materials because the question did not include enough named candidates."
        return "Material comparison from the demo ranking model:\n" + "\n".join(
            f"{item['name']} | weighted score {item['weighted_score']} | sustainability {item['scores']['sustainability']} | recyclability {item['scores']['recyclability']}"
            for item in results[:4]
        )
