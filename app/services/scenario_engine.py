from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.repositories.graph_repository import LocalGraphRepository


class ScenarioEngine:
    def __init__(self, repository: LocalGraphRepository):
        self.repository = repository

    def run(
        self,
        scenario: str,
        material_id: str | None = None,
        supplier_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = options or {}
        scenario_type = self._normalize_scenario_type(scenario, options)

        if scenario_type == "supplier_outage":
            return self._supplier_outage(
                supplier_id=supplier_id or options.get("supplier_id"),
                material_id=material_id or options.get("material_id"),
                scope=options.get("scope", "material"),
            )
        if scenario_type == "regulation_activation":
            return self._regulation_activation(
                material_id=material_id or options.get("material_id"),
                regulation_id=options.get("regulation_id"),
                scope=options.get("scope", "material"),
            )
        if scenario_type == "reformulation_target":
            return self._reformulation_target(
                material_id=material_id or options.get("material_id"),
                metric=options.get("metric", "recyclability_score"),
                target_value=int(options.get("target_value", 80)),
            )
        if scenario_type == "cost_constraint":
            return self._cost_constraint(
                material_id=material_id or options.get("material_id"),
                max_cost=float(options.get("max_cost", 4.25)),
                percent_increase=int(options.get("percent_increase", 0)),
            )

        return {
            "scenario": scenario_type,
            "summary": "Scenario not recognized by the reviewed simulation library.",
            "actions": [],
            "impacts": [],
            "metrics": {},
        }

    def _normalize_scenario_type(self, scenario: str, options: dict[str, Any]) -> str:
        explicit = str(options.get("scenario_type") or scenario or "").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "supplier_unavailable": "supplier_outage",
            "supplier_outage": "supplier_outage",
            "supplier_failure": "supplier_outage",
            "regulation_next_quarter": "regulation_activation",
            "regulation_activation": "regulation_activation",
            "upcoming_regulation": "regulation_activation",
            "compost_priority": "reformulation_target",
            "reformulation_target": "reformulation_target",
            "cost_increase": "cost_constraint",
            "cost_constraint": "cost_constraint",
            "cost_cap": "cost_constraint",
        }
        if explicit in aliases:
            return aliases[explicit]

        normalized = str(scenario or "").lower()
        if "supplier" in normalized and ("outage" in normalized or "unavailable" in normalized):
            return "supplier_outage"
        if "regulation" in normalized and ("activate" in normalized or "next quarter" in normalized):
            return "regulation_activation"
        if "reform" in normalized or ("compost" in normalized and "priority" in normalized):
            return "reformulation_target"
        if "cost" in normalized:
            return "cost_constraint"
        return explicit or "unknown"

    def _supplier_outage(self, supplier_id: str | None, material_id: str | None, scope: str) -> dict[str, Any]:
        materials = self._scenario_materials(material_id, scope)
        impacted = []
        total_loss = 0
        zero_backup = 0

        for material in materials:
            candidate_suppliers = material["supplier_ids"]
            removed_supplier = supplier_id or candidate_suppliers[0]
            if removed_supplier not in candidate_suppliers:
                continue

            remaining = [item for item in candidate_suppliers if item != removed_supplier]
            total_loss += 1
            if not remaining:
                zero_backup += 1

            substitutes = self.repository.find_recyclable_substitutes(material["material_id"])
            impacted.append(
                {
                    "material_id": material["material_id"],
                    "name": material["name"],
                    "lost_supplier_id": removed_supplier,
                    "remaining_supplier_count": len(remaining),
                    "remaining_suppliers": [self._supplier_name(item) for item in remaining],
                    "backup_gap": "none" if remaining else "critical",
                    "recommended_substitutes": [item["name"] for item in substitutes[:3]],
                }
            )

        removed_name = self._supplier_name(supplier_id) if supplier_id else "the primary supplier"
        return {
            "scenario": "supplier_outage",
            "summary": f"Simulated outage for {removed_name} across {len(impacted)} impacted materials.",
            "actions": [
                "Shift volume to remaining qualified suppliers where coverage exists.",
                "Open shortlist review for materials with no direct backup coverage.",
                "Escalate evidence refresh for substitutes before supplier reassignment.",
            ],
            "metrics": {
                "materials_impacted": len(impacted),
                "supplier_links_lost": total_loss,
                "materials_without_backup": zero_backup,
            },
            "impacts": impacted[:12],
        }

    def _regulation_activation(self, material_id: str | None, regulation_id: str | None, scope: str) -> dict[str, Any]:
        materials = self._scenario_materials(material_id, scope)
        regulation = self.repository.regulation_index.get(regulation_id) if regulation_id else self._next_inactive_regulation()
        if not regulation:
            return {
                "scenario": "regulation_activation",
                "summary": "No pending regulation was available for simulation.",
                "actions": [],
                "impacts": [],
                "metrics": {},
            }

        impacted = []
        watch_count = 0
        non_compliant_count = 0
        for material in materials:
            projected_state = self._project_regulation_state(material, regulation)
            if projected_state == material["compliance_state"]:
                continue
            if projected_state == "watch":
                watch_count += 1
            if projected_state == "non-compliant":
                non_compliant_count += 1
            impacted.append(
                {
                    "material_id": material["material_id"],
                    "name": material["name"],
                    "current_state": material["compliance_state"],
                    "projected_state": projected_state,
                    "regulation": regulation["name"],
                    "reason": self._regulation_impact_reason(material, regulation),
                }
            )

        return {
            "scenario": "regulation_activation",
            "summary": f"Projected activation of {regulation['name']} with {len(impacted)} materials changing status.",
            "actions": [
                "Refresh supplier declarations and source evidence for exposed materials.",
                "Move projected non-compliant materials into immediate reformulation review.",
                "Pre-brief compliance owners on the upcoming state changes before the effective date.",
            ],
            "metrics": {
                "materials_impacted": len(impacted),
                "projected_watch": watch_count,
                "projected_non_compliant": non_compliant_count,
                "effective_date": regulation["effective_date"],
            },
            "impacts": impacted[:12],
        }

    def _reformulation_target(self, material_id: str | None, metric: str, target_value: int) -> dict[str, Any]:
        material = self.repository.get_material(material_id) if material_id else None
        if not material:
            return {
                "scenario": "reformulation_target",
                "summary": "Material not found for reformulation simulation.",
                "actions": [],
                "impacts": [],
                "metrics": {},
            }

        current_value = int(material.get(metric, 0))
        gap = max(0, target_value - current_value)
        candidates = [
            item for item in self.repository.list_materials()
            if int(item.get(metric, 0)) >= target_value and item["material_id"] != material["material_id"]
        ]
        candidates = sorted(
            candidates,
            key=lambda item: (
                abs(item["sustainability_score"] - material["sustainability_score"]),
                item["cost_range"]["high"],
            ),
        )

        return {
            "scenario": "reformulation_target",
            "summary": (
                f"Tested reformulation target for {material['name']} against "
                f"{self._metric_label(metric)} >= {target_value}."
            ),
            "actions": [
                "Advance candidate substitutes that already satisfy the target metric.",
                "Validate whether the target can be met without breaking cost or food-contact constraints.",
                "Capture rationale for any tradeoff between target attainment and qualified supply coverage.",
            ],
            "metrics": {
                "current_metric": current_value,
                "target_metric": target_value,
                "gap_to_target": gap,
                "qualified_alternatives": len(candidates),
            },
            "impacts": [
                {
                    "material_id": material["material_id"],
                    "name": material["name"],
                    "metric": self._metric_label(metric),
                    "current_value": current_value,
                    "target_value": target_value,
                    "gap_to_target": gap,
                    "status": "meets target" if gap == 0 else "reformulation required",
                    "recommended_substitutes": [
                        {
                            "material_id": item["material_id"],
                            "name": item["name"],
                            "metric_value": item.get(metric, 0),
                            "sustainability_score": item["sustainability_score"],
                            "cost_high": item["cost_range"]["high"],
                        }
                        for item in candidates[:5]
                    ],
                }
            ],
        }

    def _cost_constraint(self, material_id: str | None, max_cost: float, percent_increase: int) -> dict[str, Any]:
        material = self.repository.get_material(material_id) if material_id else None
        if not material:
            return {
                "scenario": "cost_constraint",
                "summary": "Material not found for cost simulation.",
                "actions": [],
                "impacts": [],
                "metrics": {},
            }

        revised = deepcopy(material["cost_range"])
        if percent_increase:
            revised["low"] = round(revised["low"] * (1 + percent_increase / 100), 2)
            revised["high"] = round(revised["high"] * (1 + percent_increase / 100), 2)

        within_limit = revised["high"] <= max_cost
        alternatives = [
            item for item in self.repository.list_materials()
            if item["material_id"] != material["material_id"] and item["cost_range"]["high"] <= max_cost
        ]
        alternatives = sorted(
            alternatives,
            key=lambda item: (
                item["cost_range"]["high"],
                -item["sustainability_score"],
            ),
        )

        return {
            "scenario": "cost_constraint",
            "summary": (
                f"Simulated cost ceiling for {material['name']} at {max_cost:.2f} USD/kg"
                + (f" after a {percent_increase}% increase." if percent_increase else ".")
            ),
            "actions": [
                "Re-rank candidates that remain below the cost ceiling.",
                "Review whether the lower-cost options preserve performance and compliance fit.",
                "Escalate supplier negotiations if the incumbent is only marginally above target.",
            ],
            "metrics": {
                "current_high_cost": material["cost_range"]["high"],
                "simulated_high_cost": revised["high"],
                "max_cost": max_cost,
                "within_constraint": "yes" if within_limit else "no",
                "qualified_lower_cost_options": len(alternatives),
            },
            "impacts": [
                {
                    "material_id": material["material_id"],
                    "name": material["name"],
                    "before": material["cost_range"],
                    "after": revised,
                    "within_constraint": within_limit,
                    "recommended_substitutes": [
                        {
                            "material_id": item["material_id"],
                            "name": item["name"],
                            "cost_high": item["cost_range"]["high"],
                            "recyclability_score": item["recyclability_score"],
                            "sustainability_score": item["sustainability_score"],
                        }
                        for item in alternatives[:5]
                    ],
                }
            ],
        }

    def _scenario_materials(self, material_id: str | None, scope: str) -> list[dict[str, Any]]:
        if material_id and scope != "portfolio":
            material = self.repository.material_index.get(material_id)
            return [material] if material else []
        return self.repository.list_materials()

    def _next_inactive_regulation(self) -> dict[str, Any] | None:
        pending = [item for item in self.repository.regulations if not item["active"]]
        pending.sort(key=lambda item: item["effective_date"])
        return pending[0] if pending else None

    def _project_regulation_state(self, material: dict[str, Any], regulation: dict[str, Any]) -> str:
        focus = regulation["focus"]
        if focus == "food-contact":
            return material["compliance_state"] if material["food_contact_safe"] else "non-compliant"
        if focus == "recyclability":
            if material["recyclability_score"] < 55:
                return "non-compliant"
            if material["recyclability_score"] < 72:
                return "watch"
            return material["compliance_state"]
        if focus == "compostability":
            if material["compostability_score"] < 50:
                return "non-compliant"
            if material["compostability_score"] < 70:
                return "watch"
            return material["compliance_state"]
        if focus == "barrier":
            if material["moisture_barrier"] < 60 and material["oxygen_barrier"] < 65:
                return "watch"
            return material["compliance_state"]
        if focus in {"seal", "adhesive", "coating"}:
            if material["seal_strength"] < 70:
                return "watch"
            return material["compliance_state"]
        if focus == "supplier":
            scores = [
                self.repository.supplier_index[supplier_id]["disruption_risk_score"]
                for supplier_id in material["supplier_ids"]
                if supplier_id in self.repository.supplier_index
            ]
            if scores and max(scores) >= 72:
                return "watch"
        return material["compliance_state"]

    def _regulation_impact_reason(self, material: dict[str, Any], regulation: dict[str, Any]) -> str:
        focus = regulation["focus"]
        if focus == "food-contact":
            return "Food-contact approval is not strong enough for the projected rule."
        if focus == "recyclability":
            return f"Recyclability score {material['recyclability_score']} sits below the projected threshold."
        if focus == "compostability":
            return f"Compostability score {material['compostability_score']} sits below the projected threshold."
        if focus == "barrier":
            return "Barrier performance may not support the stricter labeling or evidence requirement."
        if focus in {"seal", "adhesive", "coating"}:
            return "Seal or coating performance may require new declarations or formulation evidence."
        if focus == "supplier":
            return "Supplier-risk disclosure would elevate monitoring requirements for the current supply base."
        return "Projected policy activation introduces additional review requirements."

    def _supplier_name(self, supplier_id: str | None) -> str:
        if not supplier_id:
            return "unknown supplier"
        supplier = self.repository.supplier_index.get(supplier_id)
        return supplier["name"] if supplier else supplier_id

    def _metric_label(self, metric: str) -> str:
        labels = {
            "recyclability_score": "Recyclability",
            "compostability_score": "Compostability",
            "sustainability_score": "Sustainability",
            "oxygen_barrier": "Oxygen barrier",
            "moisture_barrier": "Moisture barrier",
            "seal_strength": "Seal strength",
            "thermal_tolerance": "Thermal tolerance",
        }
        return labels.get(metric, metric.replace("_", " ").title())
