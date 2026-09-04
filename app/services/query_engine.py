from __future__ import annotations

import re
import hashlib
import time
from typing import Any

from app.core.config import get_settings
from app.core.runtime_db import build_runtime_db
from app.repositories.graph_repository import GraphConnectionError, GraphQueryFailure, LocalGraphRepository
from app.services.agent_memory import ProjectMemoryStore
from app.services.agent_orchestrator import AgentOrchestrationRecorder
from app.services.agent_review import ReviewCandidateStore
from app.services.agent_tools import AgentToolbelt
from app.services.entity_resolution_agent import EntityResolutionAgent
from app.services.evidence_agent import EvidenceAgent
from app.services.investigation_planner import InvestigationPlanner
from app.services.private_data_service import PrivateDataService
from app.services.query_context import QueryContextAdapter
from app.services.query_execution_layer import QueryExecutionLayer
from app.services.query_planner import QueryPlanner
from app.services.query_response_builder import QueryResponseBuilder
from app.services.query_result_formatter import QueryResultFormatter
from app.services.scenario_engine import ScenarioEngine
from app.services.source_intake_service import SourceIntakeService


class QueryEngine:
    def __init__(
        self,
        repository: LocalGraphRepository,
        private_data: PrivateDataService | None = None,
        source_intake: SourceIntakeService | None = None,
    ):
        self.repository = repository
        self.private_data = private_data
        self.source_intake = source_intake
        self.settings = getattr(repository, "settings", get_settings())
        self.runtime_db = build_runtime_db(self.settings)
        self.planner = QueryPlanner()
        self.scenarios = ScenarioEngine(repository)
        self.review_store = ReviewCandidateStore(self.settings, self.runtime_db)
        self.project_memory = ProjectMemoryStore(self.settings)
        self.evidence_agent = EvidenceAgent()
        self.entity_resolution = EntityResolutionAgent(self.settings)
        self.investigation_planner = InvestigationPlanner()
        self.agent_tools = AgentToolbelt(repository, self.review_store)
        self.agent_orchestration = AgentOrchestrationRecorder(self.settings)
        self.context_adapter = QueryContextAdapter()
        self.result_formatter = QueryResultFormatter(repository)
        self.response_builder = QueryResponseBuilder(repository)
        self.execution_layer = QueryExecutionLayer(repository, self.result_formatter)

    def ask(
        self,
        question: str,
        options: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        mode: str = "quick_ask",
    ) -> dict[str, Any]:
        started_at = time.perf_counter()
        options = options or {}
        options = {**options, "chat_mode": mode}
        resolved_question = self._merge_context_into_question(question, context)
        plan = self.planner.plan(resolved_question, self.repository, context)
        plan.setdefault("entities", {})["chat_mode"] = mode
        private_status = self.private_data.private_status() if self.private_data else {"private_data_active": False, "dataset_count": 0, "record_count": 0}
        private_lookup = self.private_data.query(resolved_question) if self.private_data and private_status["private_data_active"] else {"rows": []}
        source_lookup = self.source_intake.search(resolved_question) if self.source_intake else {"rows": []}
        intent = plan["intent"]
        router = "source_intake" if self._should_route_to_source_intake(resolved_question, source_lookup) else self._route_question(plan, private_lookup)
        classifier = self._build_classifier_metadata(plan, router, private_status)
        retrieval = self._build_retrieval_metadata(plan, private_lookup)
        retrieval["source_intake"] = {"matched_records": len(source_lookup.get("rows", []))}
        tool_runs: list[dict[str, Any]] = []

        classify = self.agent_tools.classify_question(resolved_question, plan)
        tool_runs.append(classify)
        proof_requested = classify["output"]["proof_requested"]

        resolved = self.agent_tools.resolve_entities(resolved_question, plan)
        tool_runs.append(resolved)

        template = self.agent_tools.retrieve_reviewed_template(plan)
        tool_runs.append(template)
        template_name = template["output"]["name"]

        search_keywords = resolved["output"]["keywords"]
        primary_keyword = search_keywords[0] if search_keywords else ""
        if intent in {"compare_suppliers", "supplier_risk_ranking"}:
            search_result = self.agent_tools.search_suppliers(primary_keyword, plan.get("entities", {}).get("region"))
        else:
            search_result = self.agent_tools.search_entities(primary_keyword or resolved_question)
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
                context=context,
                resolved_question=resolved_question,
                started_at=started_at,
            )
            if router == "source_intake" and source_lookup["rows"]:
                return self._source_intake_response(
                    question,
                    plan,
                    source_lookup,
                    classifier,
                    retrieval,
                    tool_runs,
                    proof_requested,
                    router,
                    template_name,
                    context=context,
                    resolved_question=resolved_question,
                    started_at=started_at,
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
                context=context,
                resolved_question=resolved_question,
                started_at=started_at,
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
                context=context,
                resolved_question=resolved_question,
                started_at=started_at,
            )
        if router == "source_intake" and source_lookup["rows"]:
            return self._source_intake_response(
                question,
                plan,
                source_lookup,
                classifier,
                retrieval,
                tool_runs,
                proof_requested,
                router,
                template_name,
                context=context,
                resolved_question=resolved_question,
                started_at=started_at,
            )

        entities = {**plan.get("entities", {}), **self._entities_from_context(context), **options}
        result, message, source = self.execution_layer.execute(question, intent, entities, private_lookup)
        if intent == "catalog_lookup" and private_lookup["rows"]:
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
                context=context,
                resolved_question=resolved_question,
                started_at=started_at,
            )
        if source_lookup["rows"] and (source == "fallback" or self._source_intake_question(resolved_question)):
            return self._source_intake_response(
                question,
                plan,
                source_lookup,
                classifier,
                retrieval,
                tool_runs,
                proof_requested,
                "source_intake",
                template_name,
                context=context,
                resolved_question=resolved_question,
                started_at=started_at,
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
                context=context,
                resolved_question=resolved_question,
                started_at=started_at,
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
            context=context,
            resolved_question=resolved_question,
            started_at=started_at,
        )

    def enrich(self, question: str, options: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        options = options or {}
        plan = self.planner.plan(self._merge_context_into_question(question, context), self.repository, context)
        request = self._build_enrichment_request(question, plan, context, [])
        review_tool = self.agent_tools.create_review_candidate(
            "graph_enrichment_request",
            "Potential graph data gap should be reviewed before any KG write-back.",
            {"enrichment_request": request, "options": options},
        )
        return {
            "status": "staged_for_review",
            "enrichment_request": request,
            "review_candidate": review_tool["output"],
            "writeback_allowed": False,
        }

    def workflow_status(self) -> dict[str, Any]:
        templates = [
            {"intent": "suppliers_for_material", "description": "List qualified suppliers for a selected material.", "parameters": ["material_id"]},
            {"intent": "selected_supplier_lookup", "description": "Open a direct supplier profile from selected context.", "parameters": ["supplier_id"]},
            {"intent": "evidence_for_material", "description": "Trace source documents, lab reports, and declarations.", "parameters": ["material_id"]},
            {"intent": "find_recyclable_substitutes", "description": "Find substitute materials and rank tradeoffs.", "parameters": ["material_id"]},
            {"intent": "compare_materials", "description": "Compare materials by weighted performance and sustainability.", "parameters": ["material_ids"]},
            {"intent": "catalog_lookup", "description": "Search local catalog/private/uploaded records.", "parameters": ["query"]},
        ]
        return {
            "status": "ready",
            "chat_modes": [
                {"id": "quick_ask", "label": "Quick Ask", "description": "Direct graph questions with selected context."},
                {"id": "research_review", "label": "Research Review", "description": "Deeper fit, risk, evidence, and provenance review."},
            ],
            "follow_up_suggestions": [
                "Show suppliers for this",
                "Show evidence for this",
                "Compare this to alternatives",
                "What data is missing for this decision?",
            ],
            "reviewed_templates": templates,
            "writebacks": {"enabled": False, "policy": "enrichment requests are staged for human review"},
        }

    def run_scenario(self, scenario: str, material_id: str | None = None, supplier_id: str | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.scenarios.run(scenario=scenario, material_id=material_id, supplier_id=supplier_id, options=options)

    def _recommend_materials(self, question: str, entities: dict[str, Any]) -> list[dict[str, Any]]:
        return self.execution_layer.recommend_materials(entities)

    def _filter_materials_from_question(self, entities: dict[str, Any]) -> list[dict[str, Any]]:
        return self.execution_layer.filter_materials_from_question(entities)

    def _entities_from_context(self, context: dict[str, Any] | None) -> dict[str, Any]:
        return self.context_adapter.entities_from_context(context)

    def _merge_context_into_question(self, question: str, context: dict[str, Any] | None) -> str:
        return self.context_adapter.merge_context_into_question(question, context)

    def _summarize_selected_material_lookup(self, material: dict[str, Any] | None, material_id: str | None) -> str:
        return self.result_formatter.summarize_selected_material_lookup(material, material_id)

    def _summarize_selected_supplier_lookup(self, supplier: dict[str, Any] | None, supplier_id: str | None) -> str:
        return self.result_formatter.summarize_selected_supplier_lookup(supplier, supplier_id)

    def _summarize_selected_entity_lookup(self, payload: dict[str, Any] | None) -> str:
        return self.result_formatter.summarize_selected_entity_lookup(payload)

    def _summarize_uploaded_record_lookup(self, payload: dict[str, Any] | None) -> str:
        return self.result_formatter.summarize_uploaded_record_lookup(payload)

    def _summarize_material_list(self, materials: list[dict[str, Any]], intro: str) -> str:
        return self.result_formatter.summarize_material_list(materials, intro)

    def _summarize_supplier_list(self, suppliers: list[dict[str, Any]], intro: str) -> str:
        return self.result_formatter.summarize_supplier_list(suppliers, intro)

    def _summarize_risk_materials(self, materials: list[dict[str, Any]]) -> str:
        return self.result_formatter.summarize_risk_materials(materials)

    def _summarize_evidence(self, payload: dict[str, Any]) -> str:
        return self.result_formatter.summarize_evidence(payload)

    def _summarize_material_detail(self, material: dict[str, Any] | None) -> str:
        return self.result_formatter.summarize_material_detail(material)

    def _summarize_comparison(self, results: list[dict[str, Any]]) -> str:
        return self.result_formatter.summarize_comparison(results)

    def _route_question(self, plan: dict[str, Any], private_lookup: dict[str, Any]) -> str:
        return self.response_builder.route_question(plan, private_lookup)

    def _source_intake_question(self, question: str) -> bool:
        lowered = question.lower()
        return any(
            marker in lowered
            for marker in [
                "uploaded",
                "source",
                "json",
                "pdf",
                "file",
                "schema",
                "extracted",
                "document",
                "record",
                "component",
            ]
        )

    def _should_route_to_source_intake(self, question: str, source_lookup: dict[str, Any]) -> bool:
        return bool(source_lookup.get("rows")) and self._source_intake_question(question)

    def _build_classifier_metadata(self, plan: dict[str, Any], router: str, private_status: dict[str, Any]) -> dict[str, Any]:
        return self.response_builder.build_classifier_metadata(plan, router, private_status)

    def _build_retrieval_metadata(self, plan: dict[str, Any], private_lookup: dict[str, Any]) -> dict[str, Any]:
        return self.response_builder.build_retrieval_metadata(plan, private_lookup)

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
        return self.result_formatter.normalize_result_rows(result, source)

    def _review_gate(self, classifier: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
        return self.response_builder.review_gate(classifier, rows)

    def _pipeline_trace(self, classifier: dict[str, Any], retrieval: dict[str, Any], rows: list[dict[str, Any]], message: str, review: dict[str, Any]) -> list[dict[str, Any]]:
        return self.response_builder.pipeline_trace(classifier, retrieval, rows, message, review)

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
        context: dict[str, Any] | None = None,
        resolved_question: str | None = None,
        started_at: float | None = None,
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
            context=context,
            resolved_question=resolved_question,
            started_at=started_at,
        )

    def _source_intake_response(
        self,
        question: str,
        plan: dict[str, Any],
        source_lookup: dict[str, Any],
        classifier: dict[str, Any],
        retrieval: dict[str, Any],
        tool_runs: list[dict[str, Any]],
        proof_requested: bool,
        route: str,
        template_name: str,
        context: dict[str, Any] | None = None,
        resolved_question: str | None = None,
        started_at: float | None = None,
    ) -> dict[str, Any]:
        result = {"rows": source_lookup["rows"], "source_query": source_lookup.get("query", {})}
        top_rows = source_lookup["rows"][:5]
        message = "Uploaded source intake found reusable local records for this question:\n" + "\n".join(
            f"{item['label']} | {item['source_type']} | score {item['score']}" for item in top_rows
        )
        return self._finalize_response(
            question=question,
            plan={**plan, "intent": "source_intake_lookup"},
            intent="catalog_lookup",
            result=result,
            message=message,
            classifier={**classifier, "route": "source_intake"},
            retrieval=retrieval,
            source="source_intake",
            tool_runs=tool_runs,
            proof_requested=proof_requested,
            route=route,
            template_name=template_name,
            context=context,
            resolved_question=resolved_question,
            started_at=started_at,
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
        context: dict[str, Any] | None = None,
        resolved_question: str | None = None,
        started_at: float | None = None,
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
        investigation_plan = self.investigation_planner.build_plan(resolved_question or question, intent, plan.get("entities", {}))

        review_candidate = None
        if (proof_requested and evidence_profile["evidence_strength"] == "weak") or entity_resolution["review_before_merge"]:
            review_tool = self.agent_tools.create_review_candidate(
                "evidence_gap" if missing_evidence else "entity_resolution",
                missing_evidence[0] if missing_evidence else "Potential duplicate or alias resolution requires human review.",
                {
                    "question": resolved_question or question,
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
        latency_ms = int((time.perf_counter() - started_at) * 1000) if started_at else 0
        enrichment_request = self._build_enrichment_request(resolved_question or question, plan, context, scored_rows) if not scored_rows else None
        empty_state = self._build_empty_state(intent, route, enrichment_request) if not scored_rows else {}
        route_preview = {
            "route": route,
            "intent": intent,
            "template": template_name,
            "context_entity": self._context_label(context),
            "mode": (plan.get("entities", {}) or {}).get("chat_mode") or "quick_ask",
        }
        answer_quality = {
            "status": "no_verified_rows" if not scored_rows else "answered",
            "row_count": len(scored_rows),
            "evidence_strength": evidence_profile.get("evidence_strength", "unknown"),
            "needs_review": bool(review_candidate or enrichment_request),
        }
        provenance = {
            "verified_kg": [row for row in scored_rows if not self._is_provisional_row(row)],
            "provisional": [row for row in scored_rows if self._is_provisional_row(row)],
            "evidence_rows": evidence_rows,
        }
        panel["debug"] = {
            "source": source,
            "classifier": classifier,
            "retrieval": retrieval,
            "scoring": scoring,
            "review": review,
        }
        project_memory = self.project_memory.update(
            {
                "prior_questions": [resolved_question or question],
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
                "uploaded_file_references": [
                    row.get("entity_id")
                    for row in scored_rows
                    if row.get("entity_type") == "uploaded_record" and row.get("entity_id")
                ],
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
        self.agent_orchestration.append_audit(resolved_question or question, orchestration, review_candidate)
        return {
            "question": question,
            "resolved_question": resolved_question or question,
            "context": context or {},
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
            "source_intake": result.get("source_query", {}) if isinstance(result, dict) and source == "source_intake" else {},
            "route_preview": route_preview,
            "answer_quality": answer_quality,
            "empty_state": empty_state,
            "results": scored_rows,
            "confidence": float(classifier.get("confidence", 0)),
            "latency_ms": latency_ms,
            "provenance": provenance,
            "execution_metadata": {
                "template": template_name,
                "route": route,
                "intent": intent,
                "latency_ms": latency_ms,
                "provisional_writeback_enabled": False,
            },
            "enrichment_request": enrichment_request,
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
        return self.response_builder.build_answer_panel(intent, result, plan, message)

    def _build_empty_state(self, intent: str, route: str, enrichment_request: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "title": "No verified graph rows found",
            "message": "The query ran, but PackGraph could not find a verified relationship for this request.",
            "intent": intent,
            "route": route,
            "next_action": "Review the staged enrichment request before adding anything to the graph." if enrichment_request else "Try a narrower material, supplier, or evidence question.",
        }

    def _build_enrichment_request(
        self,
        query: str,
        plan: dict[str, Any],
        context: dict[str, Any] | None,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if rows:
            return None
        source = self._context_label(context) or plan.get("entities", {}).get("material_id") or "unknown_source"
        target = self._target_from_question(query)
        relationship = self._relationship_for_intent(plan.get("intent", "unknown"))
        edge_key_raw = f"{source}|{relationship}|{target}|{query}".lower()
        return {
            "source": source,
            "relationship": relationship,
            "target": target,
            "confidence": 0.36,
            "evidence": [],
            "query": query,
            "model": "packgraph-local-enrichment-stub",
            "edge_key": hashlib.sha256(edge_key_raw.encode("utf-8")).hexdigest()[:16],
        }

    def _relationship_for_intent(self, intent: str) -> str:
        mapping = {
            "suppliers_for_material": "SUPPLIED_BY",
            "evidence_for_material": "HAS_DOCUMENT",
            "find_recyclable_substitutes": "SUBSTITUTES_WITH",
            "compare_materials": "COMPARES_WITH",
            "selected_supplier_lookup": "SUPPLIES",
            "selected_material_lookup": "RELATED_TO",
        }
        return mapping.get(intent, "NEEDS_REVIEW_RELATIONSHIP")

    def _target_from_question(self, query: str) -> str:
        tokens = [token for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", query) if token.lower() not in {"show", "what", "where", "with", "this", "that", "about", "source"}]
        return " ".join(tokens[-4:]) or "unknown_target"

    def _context_label(self, context: dict[str, Any] | None) -> str:
        if not context:
            return ""
        return context.get("entity_id") or context.get("entity_name") or context.get("entity_type") or ""

    def _is_provisional_row(self, row: dict[str, Any]) -> bool:
        return (
            row.get("source_type") == "llm_inferred"
            or row.get("assertion_kind") == "LLM_INFERRED"
            or row.get("validation_status") == "pending"
        )
