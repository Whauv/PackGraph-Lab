from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from adk_architecture.tool_runtime import get_packgraph_state


class LocalFunctionTool:
    """Local-first compatibility wrapper for environments that do not need live Google ADK."""

    def __init__(self, fn):
        self._fn = fn
        self.name = fn.__name__

    def run_sync(self, args: dict[str, Any] | None = None, tool_context=None):
        return self._fn(**(args or {}))

    async def run_async(self, args: dict[str, Any] | None = None, tool_context=None):
        return self.run_sync(args=args, tool_context=tool_context)


def _function_tool_factory():
    use_google_adk = os.getenv("PACKGRAPH_USE_GOOGLE_ADK_RUNTIME", "").lower() in {"1", "true", "yes"}
    if use_google_adk:
        from google.adk.tools.function_tool import FunctionTool as GoogleFunctionTool  # pragma: no cover - optional dependency path

        return GoogleFunctionTool
    return LocalFunctionTool


def health_summary() -> dict[str, Any]:
    """Return a PackGraph runtime summary without mutating state."""
    state = get_packgraph_state()
    return {
        "service": state.settings.project_name,
        "backend": state.settings.graph_backend,
        "private_data_active": state.private_data.has_data(),
        "runtime_db": state.runtime_db.health(),
        "job_summary": state.jobs.summary(),
    }


def list_materials(limit: int = 200) -> list[dict[str, Any]]:
    """List materials from the existing PackGraph repository."""
    state = get_packgraph_state()
    return state.repository.list_materials()[:limit]


def get_material(material_id: str) -> dict[str, Any] | None:
    """Fetch one material by ID from the existing repository."""
    state = get_packgraph_state()
    return state.repository.get_material(material_id)


def list_suppliers(region: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    """List suppliers, optionally filtered by region."""
    state = get_packgraph_state()
    return state.repository.list_suppliers(region=region)[:limit]


def classify_question(question: str) -> dict[str, Any]:
    """Classify a natural-language question using PackGraph's deterministic planner."""
    state = get_packgraph_state()
    plan = state.query_engine.planner.plan(question, state.repository)
    return state.query_engine.agent_tools.classify_question(question, plan)


def retrieve_reviewed_template(question: str) -> dict[str, Any]:
    """Resolve the reviewed query template selected for a question."""
    state = get_packgraph_state()
    plan = state.query_engine.planner.plan(question, state.repository)
    return state.query_engine.agent_tools.retrieve_reviewed_template(plan)


def search_entities(keyword: str) -> dict[str, Any]:
    """Search graph entities using PackGraph's deterministic graph lookup."""
    state = get_packgraph_state()
    return state.query_engine.agent_tools.search_entities(keyword)


def search_suppliers(keyword: str, region: str | None = None) -> dict[str, Any]:
    """Search suppliers using PackGraph's supplier lookup path."""
    state = get_packgraph_state()
    return state.query_engine.agent_tools.search_suppliers(keyword, region)


def query_graph(question: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute the existing PackGraph query engine through an ADK function tool."""
    state = get_packgraph_state()
    return state.query_engine.ask(question, options or {})


def retrieve_source_documents(material_id: str) -> dict[str, Any]:
    """Retrieve evidence documents and test reports for a material."""
    state = get_packgraph_state()
    return state.query_engine.agent_tools.retrieve_source_documents({}, {"material_id": material_id})


def score_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Score result rows with the PackGraph deterministic scoring helper."""
    state = get_packgraph_state()
    return state.query_engine.agent_tools.score_results(rows)


def build_answer_explanation(
    message: str,
    evidence_profile: dict[str, Any],
    review_candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the explanation block returned by the PackGraph answer layer."""
    state = get_packgraph_state()
    return state.query_engine.agent_tools.build_answer_explanation(message, evidence_profile, review_candidate)


def run_scenario(
    scenario: str,
    material_id: str | None = None,
    supplier_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the existing PackGraph scenario engine without bypassing review controls."""
    state = get_packgraph_state()
    return state.query_engine.run_scenario(
        scenario=scenario,
        material_id=material_id,
        supplier_id=supplier_id,
        options=options or {},
    )


def graph_subgraph(material_id: str) -> dict[str, Any]:
    """Return the scoped graph subgraph for a material."""
    state = get_packgraph_state()
    return state.repository.graph_subgraph(material_id)


def create_review_candidate(
    candidate_type: str,
    reason: str,
    payload: dict[str, Any] | None = None,
    org_id: str = "ORG-001",
    submitted_by: str = "adk-operator",
    submitted_by_name: str = "ADK Operator",
) -> dict[str, Any]:
    """Stage a review candidate instead of writing ambiguous changes directly."""
    state = get_packgraph_state()
    safe_payload = {
        **(payload or {}),
        "submitted_by": submitted_by,
        "submitted_by_name": submitted_by_name,
        "submission_channel": "adk_architecture",
    }
    return state.review_store.create(candidate_type, reason, safe_payload, org_id=org_id)


@lru_cache(maxsize=1)
def get_adk_tools() -> list[Any]:
    tool_class = _function_tool_factory()
    return [
        tool_class(health_summary),
        tool_class(list_materials),
        tool_class(get_material),
        tool_class(list_suppliers),
        tool_class(classify_question),
        tool_class(retrieve_reviewed_template),
        tool_class(search_entities),
        tool_class(search_suppliers),
        tool_class(query_graph),
        tool_class(retrieve_source_documents),
        tool_class(score_results),
        tool_class(build_answer_explanation),
        tool_class(run_scenario),
        tool_class(graph_subgraph),
        tool_class(create_review_candidate),
    ]
