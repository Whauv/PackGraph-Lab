from __future__ import annotations

from app.core.config import get_settings
from app.repositories.graph_repository import build_graph_repository
from app.services.agent_review import ReviewCandidateStore
from app.services.query_engine import QueryEngine

try:
    from google.adk.agents import Agent
except Exception:  # pragma: no cover - optional dependency
    Agent = None


_settings = get_settings()
_repository = build_graph_repository(_settings)
_engine = QueryEngine(_repository)
_review_store = ReviewCandidateStore(_settings)


def classify_question(question: str) -> dict:
    plan = _engine.planner.plan(question, _engine.repository)
    return _engine.agent_tools.classify_question(question, plan)["output"]


def query_graph_readonly(question: str) -> dict:
    return _engine.ask(question)


def create_human_review_candidate(candidate_type: str, reason: str, payload: dict) -> dict:
    return _review_store.create(candidate_type, reason, payload)


def inspect_agent_state_machine(question: str) -> list[dict]:
    response = _engine.ask(question)
    return response["agent_state_machine"]


if Agent is not None:  # pragma: no cover - optional dependency
    agent = Agent(
        name="packgraph_lab_agent",
        description="Read-only PackGraph Lab graph assistant with reviewed templates and human-review staging.",
        tools=[
            classify_question,
            query_graph_readonly,
            create_human_review_candidate,
            inspect_agent_state_machine,
        ],
    )
