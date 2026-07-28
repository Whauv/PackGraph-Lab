from __future__ import annotations

from typing import Any


AGENT_STATES = [
    "question_received",
    "intent_classified",
    "entities_resolved",
    "tools_selected",
    "graph_queried",
    "evidence_retrieved",
    "results_scored",
    "answer_generated",
    "review_checked",
]


def build_state_machine(completed_to: str, details: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    details = details or {}
    finished = AGENT_STATES.index(completed_to) if completed_to in AGENT_STATES else len(AGENT_STATES) - 1
    state_rows = []
    for index, name in enumerate(AGENT_STATES):
        status = "completed" if index <= finished else "pending"
        state_rows.append(
            {
                "state": name,
                "status": status,
                "detail": details.get(name, ""),
            }
        )
    return state_rows
