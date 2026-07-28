from __future__ import annotations

import re
from typing import Any

from app.repositories.graph_repository import LocalGraphRepository
from app.services.agent_review import ReviewCandidateStore


STOPWORDS = {
    "a",
    "an",
    "and",
    "best",
    "find",
    "for",
    "in",
    "list",
    "me",
    "show",
    "tell",
    "the",
    "what",
    "which",
    "with",
}


def _tool_result(name: str, status: str, summary: str, output: Any) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "summary": summary,
        "output": output,
    }


class AgentToolbelt:
    def __init__(self, repository: LocalGraphRepository, review_store: ReviewCandidateStore):
        self.repository = repository
        self.review_store = review_store

    def classify_question(self, question: str, plan: dict[str, Any]) -> dict[str, Any]:
        lowered = question.casefold()
        intent = plan["intent"]
        return _tool_result(
            "classify_question",
            "ok",
            f"Classified the question as {intent}.",
            {
                "intent": intent,
                "proof_requested": any(token in lowered for token in ["proof", "source", "provenance", "evidence", "document"]),
            },
        )

    def resolve_entities(self, question: str, plan: dict[str, Any]) -> dict[str, Any]:
        tokens = [
            token
            for token in re.findall(r"[a-z0-9][a-z0-9\-/]+", question.casefold())
            if token not in STOPWORDS
        ]
        return _tool_result(
            "resolve_entities",
            "ok",
            "Extracted reviewed planner entities and deterministic keywords.",
            {
                "entities": plan.get("entities", {}),
                "keywords": tokens[:8],
            },
        )

    def retrieve_reviewed_template(self, plan: dict[str, Any]) -> dict[str, Any]:
        template = {
            "name": plan.get("cypher_template") or "READ_ONLY_REPOSITORY_LOOKUP",
            "reviewed": bool(plan.get("audit", {}).get("reviewed_template")),
            "parameters_needed": plan.get("parameters_needed", []),
        }
        return _tool_result(
            "retrieve_reviewed_template",
            "ok",
            f"Selected reviewed template {template['name']}.",
            template,
        )

    def search_entities(self, keyword: str) -> dict[str, Any]:
        rows = self.repository.global_search(keyword)[:8]
        return _tool_result("search_entities", "ok", f"Found {len(rows)} matching graph entities.", rows)

    def search_suppliers(self, keyword: str, region: str | None = None) -> dict[str, Any]:
        keyword_lower = keyword.lower().strip()
        candidates = []
        for supplier in self.repository.list_suppliers(region=region):
            haystack = " ".join([supplier["name"], supplier["country"], " ".join(supplier.get("regions_served", []))]).lower()
            if not keyword_lower or keyword_lower in haystack:
                candidates.append(supplier)
        return _tool_result("search_suppliers", "ok", f"Found {len(candidates[:8])} supplier matches.", candidates[:8])

    def query_database(self, intent: str, route: str, template_name: str) -> dict[str, Any]:
        return _tool_result(
            "query_database",
            "ok",
            f"Executed deterministic {route} retrieval for {intent} using {template_name}.",
            {
                "intent": intent,
                "route": route,
                "template_name": template_name,
                "writeback_allowed": False,
            },
        )

    def retrieve_source_documents(self, result: Any, entities: dict[str, Any]) -> dict[str, Any]:
        material_id = entities.get("material_id")
        if not material_id and isinstance(result, dict):
            material_id = result.get("material", {}).get("material_id") or result.get("material_id")
        rows: list[dict[str, Any]] = []
        if material_id:
            payload = self.repository.evidence_for_material(material_id)
            rows = [*payload.get("documents", []), *payload.get("test_reports", [])]
        return _tool_result("retrieve_source_documents", "ok", f"Retrieved {len(rows)} evidence rows.", rows[:10])

    def score_results(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        scored = []
        for index, row in enumerate(rows, start=1):
            base_score = row.get("score")
            if base_score is None and "weighted_score" in row:
                base_score = row["weighted_score"]
            elif base_score is None and "sustainability_score" in row:
                base_score = row["sustainability_score"]
            elif base_score is None:
                base_score = max(10, 100 - index)
            scored.append({**row, "rank": index, "score": round(float(base_score), 2)})
        return _tool_result("score_results", "ok", f"Scored {len(scored)} rows deterministically.", scored)

    def build_answer_explanation(self, message: str, evidence_profile: dict[str, Any], review_candidate: dict[str, Any] | None) -> dict[str, Any]:
        detail = message
        if review_candidate:
            detail = f"{message}\nReview candidate {review_candidate['candidate_id']} was created before any write-back action."
        return _tool_result(
            "build_answer_explanation",
            "ok",
            "Built the final answer explanation with evidence context.",
            {
                "summary": detail,
                "evidence_strength": evidence_profile["evidence_strength"],
            },
        )

    def create_review_candidate(self, candidate_type: str, reason: str, payload: dict[str, Any]) -> dict[str, Any]:
        candidate = self.review_store.create(candidate_type, reason, payload)
        return _tool_result(
            "create_review_candidate",
            "ok",
            "Created a human-review staging candidate.",
            candidate,
        )
