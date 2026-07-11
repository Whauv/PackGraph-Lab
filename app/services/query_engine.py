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
        plan = self.planner.plan(question)
        intent = plan["intent"]
        if intent == "refuse_or_clarify":
            return {"plan": plan, "result": None, "message": plan["audit"]["reason"]}

        result = None
        if intent == "recommend_food_packaging":
            result = self.repository.recommend_food_packaging(options.get("prioritize_sustainability", False))
        elif intent == "find_recyclable_substitutes":
            result = self.repository.find_recyclable_substitutes(options.get("material_id", "MAT-001"))
        elif intent == "compare_suppliers":
            result = self.repository.compare_suppliers(options.get("supplier_ids"))
        elif intent == "non_compliant_materials":
            result = self.repository.non_compliant_materials(options.get("regulation_id", "REGU-003"))
        elif intent == "evidence_for_material":
            result = self.repository.evidence_for_material(options.get("material_id", "MAT-001"))
        elif intent == "materials_at_risk":
            result = self.repository.materials_at_risk()

        return {
            "plan": plan,
            "result": result,
            "message": plan["explanation"],
        }

    def run_scenario(self, scenario: str, material_id: str | None = None, supplier_id: str | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.scenarios.run(scenario=scenario, material_id=material_id, supplier_id=supplier_id, options=options)
