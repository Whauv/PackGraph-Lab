from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from app.core.config import Settings
from app.services.agent_state_machine import build_state_machine
from app.services.security_utils import sanitize_audit_payload, secure_append_jsonl


class AgentOrchestrationRecorder:
    def __init__(self, settings: Settings):
        self.audit_path = settings.agent_audit_path

    def build_orchestration(
        self,
        *,
        intent: str,
        route: str,
        template_name: str,
        tool_runs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "selected_intent": intent,
            "selected_route": route,
            "selected_template": template_name,
            "tool_order": [tool["name"] for tool in tool_runs],
            "writeback_policy": "review_before_writeback",
        }

    def build_state_rows(self, route: str, intent: str, evidence_count: int, review_needed: bool) -> list[dict[str, Any]]:
        details = {
            "question_received": "Received the chat question for deterministic processing.",
            "intent_classified": f"Reviewed planner classified the question as {intent}.",
            "entities_resolved": "Entity slots and keywords were extracted from the question.",
            "tools_selected": f"Selected the {route} retrieval path and explicit toolbelt calls.",
            "graph_queried": f"Executed the {route} lookup without arbitrary Cypher generation.",
            "evidence_retrieved": f"Retrieved {evidence_count} evidence rows.",
            "results_scored": "Applied deterministic scoring and reranking.",
            "answer_generated": "Built the structured answer and explanation payload.",
            "review_checked": "Evaluated write-back safety and human-review requirements." if review_needed else "Cleared read-only presentation without write-back.",
        }
        return build_state_machine("review_checked", details)

    def append_audit(self, question: str, orchestration: dict[str, Any], review_candidate: dict[str, Any] | None) -> None:
        entry = sanitize_audit_payload({
            "timestamp": datetime.now(UTC).isoformat(),
            "question": question,
            "orchestration": orchestration,
            "review_candidate_id": review_candidate["candidate_id"] if review_candidate else None,
        })
        secure_append_jsonl(self.audit_path, entry)
