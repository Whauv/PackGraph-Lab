from __future__ import annotations

import re
from typing import Any

from app.services.selected_entity_routing import entities_from_selected_context


class QueryContextAdapter:
    def entities_from_context(self, context: dict[str, Any] | None) -> dict[str, Any]:
        return entities_from_selected_context(context)

    def merge_context_into_question(self, question: str, context: dict[str, Any] | None) -> str:
        if not context:
            return question
        entity_type = str(context.get("entity_type") or "").strip().lower()
        entity_id = context.get("entity_id")
        entity_name = context.get("entity_name")
        metadata = context.get("metadata") or {}
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
