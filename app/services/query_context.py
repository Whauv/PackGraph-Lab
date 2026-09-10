from __future__ import annotations

import re
from typing import Any

from app.services.selected_entity_routing import entities_from_selected_context


class QueryContextAdapter:
    def active_context(self, context: dict[str, Any] | None) -> dict[str, Any] | None:
        if not context:
            return None
        active = context.get("active")
        if isinstance(active, dict) and any(active.get(key) for key in ["entity_type", "entity_id", "entity_name"]):
            merged = {**active}
            history = context.get("items") or context.get("history") or active.get("history") or []
            if history:
                merged["history"] = history
            return merged
        return context

    def requirements_from_context(self, context: dict[str, Any] | None) -> dict[str, Any]:
        if not context or not isinstance(context.get("requirements"), dict):
            return {}
        return context.get("requirements") or {}

    def entities_from_context(self, context: dict[str, Any] | None) -> dict[str, Any]:
        return entities_from_selected_context(self.active_context(context))

    def merge_context_into_question(self, question: str, context: dict[str, Any] | None) -> str:
        active = self.active_context(context)
        if not active:
            return question
        entity_type = str(active.get("entity_type") or "").strip().lower()
        entity_id = active.get("entity_id")
        entity_name = active.get("entity_name")
        metadata = active.get("metadata") or {}
        if not any([entity_type, entity_id, entity_name]):
            return question
        descriptor = entity_name or entity_id or "selected item"
        if entity_type:
            descriptor = f"{entity_type} {descriptor}"
        descriptor = descriptor.strip()
        resolved = re.sub(r"\b(this|it|that|selected item|selected entity)\b", descriptor, question, flags=re.IGNORECASE)
        if resolved != question:
            return resolved
        if re.search(r"\b(show|list|find|compare|review|inspect|trace|open)\b", question.lower()):
            suffix_parts = [descriptor]
            if metadata.get("region"):
                suffix_parts.append(f"in {metadata['region']}")
            return f"{question} for {' '.join(suffix_parts)}"
        return question
