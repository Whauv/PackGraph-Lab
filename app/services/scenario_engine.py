from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.repositories.graph_repository import LocalGraphRepository


class ScenarioEngine:
    def __init__(self, repository: LocalGraphRepository):
        self.repository = repository

    def run(self, scenario: str, material_id: str | None = None, supplier_id: str | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        normalized = scenario.lower()
        if "supplier" in normalized and "unavailable" in normalized:
            return self._supplier_unavailable(supplier_id=supplier_id, material_id=material_id)
        if "cost" in normalized and "20" in normalized:
            return self._cost_increase(material_id=material_id, percent=options.get("percent", 20))
        if "compost" in normalized and "priority" in normalized:
            return self._compost_priority()
        if "regulation" in normalized and "next quarter" in normalized:
            return self._regulation_next_quarter(material_id=material_id)
        return {
            "scenario": scenario,
            "summary": "Scenario not recognized by the reviewed simulation library.",
            "actions": [],
            "impacts": [],
        }

    def _supplier_unavailable(self, supplier_id: str | None, material_id: str | None) -> dict[str, Any]:
        impacted = []
        for material in self.repository.materials:
            if supplier_id and supplier_id not in material["supplier_ids"]:
                continue
            if material_id and material["material_id"] != material_id:
                continue
            remaining = [item for item in material["supplier_ids"] if item != supplier_id]
            substitutes = self.repository.find_recyclable_substitutes(material["material_id"])
            impacted.append(
                {
                    "material_id": material["material_id"],
                    "name": material["name"],
                    "remaining_suppliers": remaining,
                    "substitute_options": [item["material_id"] for item in substitutes[:3]],
                }
            )
        return {
            "scenario": "supplier_unavailable",
            "summary": f"Simulated removal of supplier {supplier_id or 'unknown supplier'}.",
            "actions": ["Shift volume to remaining qualified suppliers", "Open an investigation on affected materials"],
            "impacts": impacted[:12],
        }

    def _cost_increase(self, material_id: str | None, percent: int) -> dict[str, Any]:
        material = self.repository.get_material(material_id) if material_id else None
        if not material:
            return {"scenario": "cost_increase", "summary": "Material not found for cost simulation.", "actions": [], "impacts": []}
        revised = deepcopy(material)
        revised["cost_range"]["low"] = round(revised["cost_range"]["low"] * (1 + percent / 100), 2)
        revised["cost_range"]["high"] = round(revised["cost_range"]["high"] * (1 + percent / 100), 2)
        substitutes = self.repository.find_recyclable_substitutes(material_id)
        return {
            "scenario": "cost_increase",
            "summary": f"Applied a {percent}% cost increase to {material['name']}.",
            "actions": ["Re-rank substitutes with lower cost exposure", "Review quarterly supplier snapshots for price compression"],
            "impacts": [{"before": material["cost_range"], "after": revised["cost_range"], "substitutes": substitutes[:5]}],
        }

    def _compost_priority(self) -> dict[str, Any]:
        ranked = self.repository.recommend_food_packaging(prioritize_sustainability=True)
        return {
            "scenario": "compost_priority",
            "summary": "Re-ranked recommendations to favor compostability and sustainability over cost.",
            "actions": ["Check industrial compost access by region", "Validate claim language against active regulations"],
            "impacts": ranked[:8],
        }

    def _regulation_next_quarter(self, material_id: str | None) -> dict[str, Any]:
        material = self.repository.get_material(material_id) if material_id else None
        risks = []
        for regulation in self.repository.regulations:
            if not regulation["active"]:
                risks.append(
                    {
                        "regulation_id": regulation["regulation_id"],
                        "name": regulation["name"],
                        "effective_date": regulation["effective_date"],
                        "possible_impact": "Review required",
                    }
                )
        return {
            "scenario": "regulation_next_quarter",
            "summary": f"Projected upcoming regulation activations for {material['name'] if material else 'the selected portfolio'}.",
            "actions": ["Check evidence gaps", "Schedule supplier declaration refresh"],
            "impacts": risks[:6],
        }
