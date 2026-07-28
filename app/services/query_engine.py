from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.repositories.graph_repository import LocalGraphRepository
from app.services.agent_memory import ProjectMemoryStore
from app.services.agent_orchestrator import AgentOrchestrationRecorder
from app.services.agent_review import ReviewCandidateStore
from app.services.agent_tools import AgentToolbelt
from app.services.entity_resolution_agent import EntityResolutionAgent
from app.services.evidence_agent import EvidenceAgent
from app.services.investigation_planner import InvestigationPlanner
from app.services.private_data_service import PrivateDataService
from app.services.query_planner import QueryPlanner
from app.services.scenario_engine import ScenarioEngine


class QueryEngine:
    def __init__(self, repository: LocalGraphRepository, private_data: PrivateDataService | None = None):
        self.repository = repository
        self.private_data = private_data
        self.settings = getattr(repository, "settings", get_settings())
        self.planner = QueryPlanner()
        self.scenarios = ScenarioEngine(repository)
        self.review_store = ReviewCandidateStore(self.settings)
        self.project_memory = ProjectMemoryStore(self.settings)
        self.evidence_agent = EvidenceAgent()
        self.entity_resolution = EntityResolutionAgent()
        self.investigation_planner = InvestigationPlanner()
        self.agent_tools = AgentToolbelt(repository, self.review_store)
        self.agent_orchestration = AgentOrchestrationRecorder(self.settings)

    def ask(self, question: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        plan = self.planner.plan(question, self.repository)
        private_status = self.private_data.private_status() if self.private_data else {"private_data_active": False, "dataset_count": 0, "record_count": 0}
        private_lookup = self.private_data.query(question) if self.private_data and private_status["private_data_active"] else {"rows": []}
        intent = plan["intent"]
        router = self._route_question(plan, private_lookup)
        classifier = self._build_classifier_metadata(plan, router, private_status)
        retrieval = self._build_retrieval_metadata(plan, private_lookup)
        tool_runs: list[dict[str, Any]] = []

        classify = self.agent_tools.classify_question(question, plan)
        tool_runs.append(classify)
        proof_requested = classify["output"]["proof_requested"]

        resolved = self.agent_tools.resolve_entities(question, plan)
        tool_runs.append(resolved)

        template = self.agent_tools.retrieve_reviewed_template(plan)
        tool_runs.append(template)
        template_name = template["output"]["name"]

        search_keywords = resolved["output"]["keywords"]
        primary_keyword = search_keywords[0] if search_keywords else ""
        if intent in {"compare_suppliers", "supplier_risk_ranking"}:
            search_result = self.agent_tools.search_suppliers(primary_keyword, plan.get("entities", {}).get("region"))
        else:
            search_result = self.agent_tools.search_entities(primary_keyword or question)
        tool_runs.append(search_result)

        query_result = self.agent_tools.query_database(intent, router, template_name)
        tool_runs.append(query_result)

        if intent == "refuse_or_clarify":
            if router == "private_data" and private_lookup["rows"]:
                return self._private_data_response(
                    question,
                    plan,
                    private_lookup,
                    classifier,
                    retrieval,
                    tool_runs,
                    proof_requested,
                    router,
                    template_name,
                )
            return self._finalize_response(
                question=question,
                plan=plan,
                intent=intent,
                result=None,
                message=plan["audit"]["reason"],
                classifier=classifier,
                retrieval=retrieval,
                tool_runs=tool_runs,
                proof_requested=proof_requested,
                route=router,
                template_name=template_name,
            )
        if router == "private_data" and private_lookup["rows"]:
            return self._private_data_response(
                question,
                plan,
                private_lookup,
                classifier,
                retrieval,
                tool_runs,
                proof_requested,
                router,
                template_name,
            )

        entities = {**plan.get("entities", {}), **options}
        result = None
        message = plan["explanation"]
        source = "graph"
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
        elif intent == "catalog_lookup" and private_lookup["rows"]:
            return self._private_data_response(
                question,
                plan,
                private_lookup,
                classifier,
                retrieval,
                tool_runs,
                proof_requested,
                router,
                template_name,
            )

        if result is None:
            if router == "private_data" and private_lookup["rows"]:
                return self._private_data_response(
                    question,
                    plan,
                    private_lookup,
                    classifier,
                    retrieval,
                    tool_runs,
                    proof_requested,
                    router,
                    template_name,
                )
            result = self.repository.materials_at_risk()
            message = self._summarize_risk_materials(result[:5])

        return self._finalize_response(
            question=question,
            plan=plan,
            intent=intent,
            result=result,
            message=message,
            classifier=classifier,
            retrieval=retrieval,
            source=source,
            tool_runs=tool_runs,
            proof_requested=proof_requested,
            route=router,
            template_name=template_name,
        )

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

    def _route_question(self, plan: dict[str, Any], private_lookup: dict[str, Any]) -> str:
        if private_lookup.get("rows") and (
            plan["intent"] in {"catalog_lookup", "refuse_or_clarify"}
            or (plan["intent"] == "compare_suppliers" and not plan.get("entities", {}).get("supplier_ids"))
            or (plan["intent"] in {"material_filter", "material_lookup"} and not plan.get("entities", {}).get("material_id"))
        ):
            return "private_data"
        return "graph"

    def _build_classifier_metadata(self, plan: dict[str, Any], router: str, private_status: dict[str, Any]) -> dict[str, Any]:
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

    def _build_retrieval_metadata(self, plan: dict[str, Any], private_lookup: dict[str, Any]) -> dict[str, Any]:
        return {
            "reviewed_template": plan.get("cypher_template"),
            "parameters_needed": plan.get("parameters_needed", []),
            "parameter_candidates": plan.get("entities", {}),
            "private_matches_found": len(private_lookup.get("rows", [])),
        }

    def _score_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        reranked = []
        for index, row in enumerate(rows, start=1):
            base_score = row.get("score")
            if base_score is None and "weighted_score" in row:
                base_score = row["weighted_score"]
            elif base_score is None and "sustainability_score" in row:
                base_score = row["sustainability_score"]
            elif base_score is None:
                base_score = max(10, 100 - index)
            reranked.append({**row, "rank": index, "score": round(float(base_score), 2)})
        return reranked

    def _normalize_result_rows(self, result: Any, source: str) -> list[dict[str, Any]]:
        if isinstance(result, list):
            rows = []
            for item in result[:10]:
                if isinstance(item, dict):
                    row = {key: value for key, value in item.items() if isinstance(value, (str, int, float, bool)) or value is None}
                    rows.append(row)
            return rows
        if isinstance(result, dict):
            rows = []
            if source == "private_data":
                for item in result.get("rows", [])[:10]:
                    rows.append(
                        {
                            "entity_type": item.get("entity_type"),
                            "label": item.get("label"),
                            "score": item.get("score"),
                            "preview": " | ".join(f"{field['label']}: {field['value']}" for field in item.get("fields", [])[:3]),
                        }
                    )
            return rows
        return []

    def _review_gate(self, classifier: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
        needs_review = classifier["route"] == "private_data" and (classifier["confidence"] < 0.8 or not rows)
        return {
            "status": "review_required" if needs_review else "cleared",
            "reason": "Low-confidence private-data match should be reviewed before any graph write-back." if needs_review else "Read-only query result is safe to present without intervention.",
            "writeback_allowed": False,
        }

    def _pipeline_trace(self, classifier: dict[str, Any], retrieval: dict[str, Any], rows: list[dict[str, Any]], message: str, review: dict[str, Any]) -> list[dict[str, Any]]:
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

    def _private_data_response(
        self,
        question: str,
        plan: dict[str, Any],
        private_lookup: dict[str, Any],
        classifier: dict[str, Any],
        retrieval: dict[str, Any],
        tool_runs: list[dict[str, Any]],
        proof_requested: bool,
        route: str,
        template_name: str,
    ) -> dict[str, Any]:
        result = {"rows": private_lookup["rows"], "private_query": private_lookup.get("query", {})}
        top_rows = private_lookup["rows"][:6]
        if top_rows:
            message = "Private data lookup returned the strongest matching records for this question:\n" + "\n".join(
                f"{item['label']} | {item['entity_type']} | score {item['score']}" for item in top_rows
            )
        else:
            message = "Private data is active, but no matching private records were found for the current question."
        return self._finalize_response(
            question=question,
            plan=plan,
            intent="catalog_lookup",
            result=result,
            message=message,
            classifier={**classifier, "route": "private_data"},
            retrieval=retrieval,
            source="private_data",
            tool_runs=tool_runs,
            proof_requested=proof_requested,
            route=route,
            template_name=template_name,
        )

    def _finalize_response(
        self,
        *,
        question: str,
        plan: dict[str, Any],
        intent: str,
        result: Any,
        message: str,
        classifier: dict[str, Any],
        retrieval: dict[str, Any],
        source: str = "graph",
        tool_runs: list[dict[str, Any]] | None = None,
        proof_requested: bool = False,
        route: str = "graph",
        template_name: str = "READ_ONLY_REPOSITORY_LOOKUP",
    ) -> dict[str, Any]:
        tool_runs = list(tool_runs or [])
        evidence_tool = self.agent_tools.retrieve_source_documents(result, plan.get("entities", {}))
        tool_runs.append(evidence_tool)
        evidence_rows = evidence_tool["output"]

        normalized_rows = self._normalize_result_rows(result, source)
        scored_tool = self.agent_tools.score_results(normalized_rows)
        tool_runs.append(scored_tool)
        scored_rows = scored_tool["output"]

        evidence_profile, missing_evidence = self.evidence_agent.build_profile(
            result=result,
            evidence_rows=evidence_rows,
            proof_requested=proof_requested,
        )
        entity_resolution = self.entity_resolution.analyze(scored_rows)
        investigation_plan = self.investigation_planner.build_plan(question, intent, plan.get("entities", {}))

        review_candidate = None
        if (proof_requested and evidence_profile["evidence_strength"] == "weak") or entity_resolution["review_before_merge"]:
            review_tool = self.agent_tools.create_review_candidate(
                "evidence_gap" if missing_evidence else "entity_resolution",
                missing_evidence[0] if missing_evidence else "Potential duplicate or alias resolution requires human review.",
                {
                    "question": question,
                    "intent": intent,
                    "route": route,
                    "top_rows": scored_rows[:3],
                    "missing_evidence": missing_evidence,
                    "entity_resolution": entity_resolution,
                },
            )
            tool_runs.append(review_tool)
            review_candidate = review_tool["output"]

        explanation_tool = self.agent_tools.build_answer_explanation(message, evidence_profile, review_candidate)
        tool_runs.append(explanation_tool)

        review = self._review_gate(classifier, scored_rows)
        scoring = {
            "strategy": "deterministic ensemble scoring",
            "row_count": len(scored_rows),
            "top_scores": [row["score"] for row in scored_rows[:5]],
        }
        trace = self._pipeline_trace(classifier, retrieval, scored_rows, message, review)
        panel = self._build_answer_panel(intent, result, plan, message)
        panel["debug"] = {
            "source": source,
            "classifier": classifier,
            "retrieval": retrieval,
            "scoring": scoring,
            "review": review,
        }
        project_memory = self.project_memory.update(
            {
                "prior_questions": [question],
                "saved_entities": [
                    row.get("entity_id") or row.get("material_id") or row.get("supplier_id") or row.get("title") or row.get("label")
                    for row in scored_rows[:5]
                ],
                "saved_suppliers": [row.get("supplier_id") or row.get("entity_id") for row in scored_rows if row.get("entity_type") == "supplier" or row.get("supplier_id")],
                "compared_entities": [
                    row.get("entity_id") or row.get("material_id")
                    for row in scored_rows[:2]
                ],
                "user_assumptions": [f"Intent {intent} routed through {route}."],
                "uploaded_file_references": [],
                "investigation_notes": [message[:180]],
            }
        )
        orchestration = self.agent_orchestration.build_orchestration(
            intent=intent,
            route=route,
            template_name=template_name,
            tool_runs=tool_runs,
        )
        agent_state_machine = self.agent_orchestration.build_state_rows(
            route=route,
            intent=intent,
            evidence_count=len(evidence_rows),
            review_needed=bool(review_candidate),
        )
        self.agent_orchestration.append_audit(question, orchestration, review_candidate)
        return {
            "plan": plan,
            "result": result,
            "message": explanation_tool["output"]["summary"],
            "panel": panel,
            "classifier": classifier,
            "retrieval": retrieval,
            "scoring": scoring,
            "review_gate": review,
            "pipeline_trace": trace,
            "rows": scored_rows,
            "private_data_active": classifier["private_data_active"],
            "source": source,
            "agent_state_machine": agent_state_machine,
            "agent_tools": tool_runs,
            "agent_orchestration": orchestration,
            "investigation_plan": investigation_plan,
            "evidence_profile": evidence_profile,
            "missing_evidence": missing_evidence,
            "project_memory": project_memory,
            "review_candidate": review_candidate,
            "entity_resolution": entity_resolution,
        }

    def _build_answer_panel(self, intent: str, result: Any, plan: dict[str, Any], message: str) -> dict[str, Any]:
        panel = {
            "title": plan.get("explanation", "Decision output"),
            "summary": message,
            "recommendations": [],
            "reasons": [],
            "risk_flags": [],
            "next_steps": [],
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
            panel["risk_flags"] = ["Declaration evidence is missing." if not any(doc.get("document_type") == "declaration" for doc in documents) else ""] if documents is not None else []
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
            panel["recommendations"] = [
                {"label": item["label"], "detail": " | ".join(f"{field['label']}: {field['value']}" for field in item.get("fields", [])[:2])}
                for item in rows[:5]
            ]
            panel["reasons"] = [
                f"Matched a private {item['entity_type']} record with score {item['score']}."
                for item in rows[:4]
            ]
            panel["risk_flags"] = ["Private records are read-only until a human review clears write-back."] if rows else ["No private match was found."]
            panel["next_steps"] = [
                "Review the matching private records before turning them into graph entities.",
                "Use the schema summary if you need to confirm available fields without exposing values.",
            ]

        if not panel["next_steps"]:
            panel["next_steps"] = [
                "Review the result in context.",
                "Move the candidate into Workbench if it deserves deeper evaluation.",
            ]
        return panel
