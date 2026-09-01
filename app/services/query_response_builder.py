from __future__ import annotations

from typing import Any

from app.services.workflow_service import WorkflowService


class QueryResponseBuilder:
    def __init__(self, repository) -> None:
        self.repository = repository
        self.workflow_service = WorkflowService()

    def route_question(self, plan: dict[str, Any], private_lookup: dict[str, Any]) -> str:
        if plan["intent"] == "uploaded_record_lookup":
            return "graph"
        if private_lookup.get("rows") and (
            plan["intent"] in {"catalog_lookup", "refuse_or_clarify"}
            or (plan["intent"] == "compare_suppliers" and not plan.get("entities", {}).get("supplier_ids"))
            or (plan["intent"] in {"material_filter", "material_lookup"} and not plan.get("entities", {}).get("material_id"))
        ):
            return "private_data"
        return "graph"

    def build_classifier_metadata(self, plan: dict[str, Any], router: str, private_status: dict[str, Any]) -> dict[str, Any]:
        entities = plan.get("entities", {})
        matched_entities = [key for key, value in entities.items() if value]
        confidence = 0.84 if plan["intent"] != "refuse_or_clarify" else 0.42
        if router == "private_data":
            confidence = max(confidence, 0.78)
        return {
            "route": router,
            "intent": plan["intent"],
            "confidence": round(confidence, 2),
            "matched_entities": matched_entities[:8],
            "private_data_active": private_status["private_data_active"],
        }

    def build_retrieval_metadata(self, plan: dict[str, Any], private_lookup: dict[str, Any]) -> dict[str, Any]:
        return {
            "reviewed_template": plan.get("cypher_template"),
            "parameters_needed": plan.get("parameters_needed", []),
            "parameter_candidates": plan.get("entities", {}),
            "private_matches_found": len(private_lookup.get("rows", [])),
        }

    def review_gate(self, classifier: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
        needs_review = classifier["route"] == "private_data" and (classifier["confidence"] < 0.8 or not rows)
        return {
            "status": "review_required" if needs_review else "cleared",
            "reason": "Low-confidence private-data match should be reviewed before any graph write-back." if needs_review else "Read-only query result is safe to present without intervention.",
            "writeback_allowed": False,
        }

    def pipeline_trace(
        self,
        classifier: dict[str, Any],
        retrieval: dict[str, Any],
        rows: list[dict[str, Any]],
        message: str,
        review: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            {"stage": "router", "status": "ok", "detail": f"Sent this question to the {classifier['route']} path."},
            {"stage": "nlp_classifier", "status": "ok", "detail": f"Intent {classifier['intent']} at confidence {classifier['confidence']}."},
            {"stage": "template_retrieval", "status": "ok", "detail": f"Reviewed template {retrieval['reviewed_template'] or 'none'}."},
            {"stage": "parameter_extraction", "status": "ok", "detail": f"Captured {len(retrieval['parameter_candidates'])} parameter slots."},
            {"stage": "cypher_execution", "status": "ok", "detail": "Executed the reviewed repository/graph retrieval path."},
            {"stage": "graph_results", "status": "ok", "detail": f"Retrieved {len(rows)} normalized rows."},
            {"stage": "ensemble_scoring_reranking", "status": "ok", "detail": "Applied deterministic reranking across the returned rows."},
            {"stage": "optional_explanation", "status": "ok", "detail": message[:160]},
            {"stage": "human_review_gate", "status": review["status"], "detail": review["reason"]},
        ]

    def build_answer_panel(self, intent: str, result: Any, plan: dict[str, Any], message: str) -> dict[str, Any]:
        workflow = self.workflow_service.for_intent(intent, result)
        panel = {
            "title": plan.get("explanation", "Decision output"),
            "summary": message,
            "recommendations": [],
            "reasons": [],
            "risk_flags": [],
            "next_steps": [],
            "recommended_action": workflow["recommended_action"],
            "workflow": workflow,
        }
        if intent in {"recommend_food_packaging", "material_filter", "find_recyclable_substitutes"} and isinstance(result, list):
            for item in result[:4]:
                material_id = item.get("material_id")
                material = self.repository.material_index.get(material_id) if material_id else None
                if not material:
                    continue
                panel["recommendations"].append(
                    {
                        "label": material["name"],
                        "detail": f"{material['category']} | sustainability {material['sustainability_score']} | recyclability {material['recyclability_score']}",
                    }
                )
                panel["reasons"].append(
                    f"{material['name']} fits with compliance {material['compliance_state']} and {len(material['supplier_ids'])} qualified suppliers."
                )
                if material["compliance_state"] != "compliant":
                    panel["risk_flags"].append(f"{material['name']} is currently {material['compliance_state']}.")
            panel["next_steps"] = [
                "Add the strongest candidates to the Workbench shortlist.",
                "Open the evidence workspace to validate declarations and lab reports.",
                "Run a scenario before moving to a final recommendation.",
            ]
        elif intent in {"compare_suppliers", "supplier_risk_ranking"} and isinstance(result, list):
            panel["recommendations"] = [
                {"label": item["name"], "detail": f"Risk {item['disruption_risk_score']} | ESG {item['esg_score']} | lead time {item['lead_time_days']} days"}
                for item in result[:4]
            ]
            panel["risk_flags"] = [f"{item['name']} has elevated disruption risk." for item in result[:2]]
            panel["next_steps"] = [
                "Review supplier snapshots and alternate supply coverage.",
                "Open graph intelligence to inspect supplier-linked materials.",
            ]
        elif intent == "evidence_for_material" and isinstance(result, dict):
            material = result.get("material")
            documents = result.get("documents", [])
            reports = result.get("test_reports", [])
            if material:
                panel["recommendations"].append(
                    {"label": material["name"], "detail": f"{len(documents)} documents and {len(reports)} test reports available"}
                )
            panel["reasons"] = [item["title"] for item in documents[:3]]
            panel["risk_flags"] = ["Declaration evidence is missing." if not any(doc.get("document_type") == "declaration" for doc in documents) else ""]
            panel["risk_flags"] = [item for item in panel["risk_flags"] if item]
            if not reports:
                panel["risk_flags"].append("No lab report was found for this material.")
            panel["next_steps"] = [
                "Inspect extracted evidence fields and missing metadata.",
                "Upload missing declarations or reports before finalizing the choice.",
            ]
        elif intent == "compare_materials" and isinstance(result, list):
            panel["recommendations"] = [
                {"label": item["name"], "detail": f"Weighted score {item['weighted_score']} | cost {item['cost_range']['high']} {item['cost_range']['currency']}"}
                for item in result[:4]
            ]
            panel["reasons"] = [
                f"{item['name']} has sustainability {item['scores']['sustainability']} and recyclability {item['scores']['recyclability']}."
                for item in result[:3]
            ]
            panel["next_steps"] = [
                "Use the side-by-side matrix to inspect detailed tradeoffs.",
                "Save the shortlist into an investigation with rationale.",
            ]
        elif intent == "catalog_lookup" and isinstance(result, dict):
            rows = result.get("rows", [])
            is_source_intake = any(item.get("entity_type") == "uploaded_record" for item in rows)
            panel["recommendations"] = [
                {
                    "label": item["label"],
                    "detail": item.get("preview")
                    or " | ".join(f"{field['label']}: {field['value']}" for field in item.get("fields", [])[:2])
                    or f"{len(item.get('schema_fields', []))} extracted schema fields",
                }
                for item in rows[:5]
            ]
            source_label = "uploaded source" if is_source_intake else "private"
            panel["reasons"] = [f"Matched a {source_label} {item['entity_type']} record with score {item['score']}." for item in rows[:4]]
            panel["risk_flags"] = [f"{source_label.title()} records are read-only until a human review clears write-back."] if rows else ["No local source match was found."]
            panel["next_steps"] = [
                "Review the matching source records before turning them into graph entities.",
                "Use the schema summary to confirm available fields and missing evidence.",
            ]
        if not panel["next_steps"]:
            panel["next_steps"] = [
                "Review the result in context.",
                "Move the candidate into Workbench if it deserves deeper evaluation.",
            ]
        panel["workflow"]["missing_evidence_count"] = len(panel["risk_flags"])
        return panel
