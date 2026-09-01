from __future__ import annotations

from typing import Any


class WorkflowService:
    """Maps query outcomes to the product decision workflow."""

    def for_intent(self, intent: str, result: Any) -> dict[str, Any]:
        action = {
            "label": "Refine on Overview",
            "target": "overview",
            "status": "discover",
            "workflow_step": "Discover",
            "reason": "Use tighter filters or a more focused question before moving forward.",
            "tone": "neutral",
        }
        if intent in {"compare_materials", "find_recyclable_substitutes", "compare_suppliers", "supplier_risk_ranking"}:
            action = {
                "label": "Open Workbench",
                "target": "workbench",
                "status": "compare",
                "workflow_step": "Compare",
                "reason": "You have enough candidate structure to compare tradeoffs side by side.",
                "tone": "success",
            }
        elif intent in {"evidence_for_material", "selected_entity_lookup", "uploaded_record_lookup"}:
            action = {
                "label": "Validate in Workbench",
                "target": "workbench",
                "status": "validate",
                "workflow_step": "Validate",
                "reason": "This answer should now be checked against evidence, extracted fields, and proof gaps.",
                "tone": "warning",
            }
        elif intent in {"material_lookup", "suppliers_for_material", "non_compliant_materials", "materials_at_risk"}:
            action = {
                "label": "Inspect in Intelligence",
                "target": "intelligence",
                "status": "validate",
                "workflow_step": "Validate",
                "reason": "The next useful step is to inspect graph context, branch relationships, and surrounding signals.",
                "tone": "warning",
            }
        elif intent == "catalog_lookup" and isinstance(result, dict) and result.get("rows"):
            action = {
                "label": "Send to Review",
                "target": "workbench",
                "status": "review",
                "workflow_step": "Review",
                "reason": "Private-data matches need human review before they can influence durable graph decisions.",
                "tone": "risk",
            }
        return {
            "current_stage": action["workflow_step"],
            "status": action["status"],
            "target": action["target"],
            "tone": action["tone"],
            "recommended_action": action,
        }
