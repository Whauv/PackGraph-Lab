from __future__ import annotations

from typing import Any


def entities_from_selected_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if not context:
        return {}
    entity_type = str(context.get("entity_type") or "").lower()
    entity_id = context.get("entity_id")
    entity_name = context.get("entity_name")
    metadata = context.get("metadata") or {}
    history = context.get("history") or []
    entities: dict[str, Any] = {}
    if entity_type == "material":
        entities["material_id"] = entity_id
    elif entity_type == "supplier":
        entities["supplier_id"] = entity_id
        entities["supplier_ids"] = [entity_id] if entity_id else []
    elif entity_type == "regulation":
        entities["regulation_id"] = entity_id
    elif entity_type == "application":
        entities["application_id"] = entity_id
    elif entity_type in {"product", "component"} and metadata.get("material_id"):
        entities["material_id"] = metadata["material_id"]
    if entity_name:
        entities["context_name"] = entity_name
        entities["selected_entity_name"] = entity_name
    if entity_type:
        entities["selected_entity_type"] = entity_type
    if entity_id:
        entities["selected_entity_id"] = entity_id
    if metadata.get("region") and not entities.get("region"):
        entities["region"] = metadata["region"]
    if history:
        entities["selected_context_history"] = history[:4]
    return {key: value for key, value in entities.items() if value not in (None, "", [])}
