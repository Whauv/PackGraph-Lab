from __future__ import annotations

from typing import Any


class WorkflowStatusService:
    def __init__(self, repository) -> None:
        self.repository = repository

    def workflow_status(self) -> dict[str, Any]:
        templates = [self.template_schema_status(item["intent"]) for item in self.template_catalog()]
        supported_suggestions = [
            item["suggestion"]
            for item in templates
            if item["schema_supported"] and item.get("suggestion")
        ]
        return {
            "status": "ready",
            "chat_modes": [
                {"id": "quick_ask", "label": "Quick Ask", "description": "Direct graph questions with selected context."},
                {"id": "research_review", "label": "Research Review", "description": "Deeper fit, risk, evidence, and provenance review."},
            ],
            "follow_up_suggestions": supported_suggestions,
            "reviewed_templates": templates,
            "writebacks": {"enabled": False, "policy": "enrichment requests are staged for human review"},
        }

    def template_catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "intent": "suppliers_for_material",
                "description": "List qualified suppliers for a selected material.",
                "parameters": ["material_id"],
                "required_labels": ["Material", "Supplier"],
                "required_relationship_type": "SUPPLIED_BY",
                "suggestion": "Show suppliers for this",
            },
            {
                "intent": "selected_supplier_lookup",
                "description": "Open a direct supplier profile from selected context.",
                "parameters": ["supplier_id"],
                "required_labels": ["Supplier"],
                "required_relationship_type": None,
                "suggestion": "Show risk for this supplier",
            },
            {
                "intent": "evidence_for_material",
                "description": "Trace source documents, lab reports, and declarations.",
                "parameters": ["material_id"],
                "required_labels": ["Material", "SourceDocument"],
                "required_relationship_type": "HAS_DOCUMENT",
                "suggestion": "Show evidence for this",
            },
            {
                "intent": "find_recyclable_substitutes",
                "description": "Find substitute materials and rank tradeoffs.",
                "parameters": ["material_id"],
                "required_labels": ["Material"],
                "required_relationship_type": "SUBSTITUTES_WITH",
                "suggestion": "Compare this to alternatives",
            },
            {
                "intent": "compare_materials",
                "description": "Compare materials by weighted performance and sustainability.",
                "parameters": ["material_ids"],
                "required_labels": ["Material"],
                "required_relationship_type": None,
                "suggestion": "Run a comparison for this",
            },
            {
                "intent": "catalog_lookup",
                "description": "Search local catalog/private/uploaded records.",
                "parameters": ["query"],
                "required_labels": [],
                "required_relationship_type": None,
                "suggestion": "What data is missing for this decision?",
            },
        ]

    def template_schema_status(self, intent: str) -> dict[str, Any]:
        template = next((item for item in self.template_catalog() if item["intent"] == intent), None)
        if not template:
            return {
                "intent": intent,
                "description": "No reviewed template matched.",
                "parameters": [],
                "required_labels": [],
                "required_relationship_type": None,
                "suggestion": "",
                "schema_supported": False,
                "blockers": [{"type": "missing_reviewed_template", "value": intent}],
            }
        available_labels = self._available_schema_labels()
        available_relationships = self._available_relationship_types()
        missing_labels = [label for label in template["required_labels"] if label not in available_labels]
        missing_relationship = template["required_relationship_type"] and template["required_relationship_type"] not in available_relationships
        blockers = []
        if missing_labels:
            blockers.append({"type": "missing_required_labels", "values": missing_labels})
        if missing_relationship:
            blockers.append({"type": "missing_required_relationship_type", "value": template["required_relationship_type"]})
        return {**template, "schema_supported": not blockers, "blockers": blockers}

    def _available_schema_labels(self) -> set[str]:
        labels = set()
        if getattr(self.repository, "materials", None):
            labels.add("Material")
        if getattr(self.repository, "suppliers", None):
            labels.add("Supplier")
        if getattr(self.repository, "documents", None):
            labels.add("SourceDocument")
        if getattr(self.repository, "applications", None):
            labels.add("Application")
        if getattr(self.repository, "regulations", None):
            labels.add("Regulation")
        return labels

    def _available_relationship_types(self) -> set[str]:
        relationships = set()
        for row in getattr(self.repository, "relationships", []) or []:
            relation = row.get("type") or row.get("relationship") or row.get("relationship_type")
            if relation:
                relationships.add(str(relation))
        relationships.update({"SUPPLIED_BY", "HAS_DOCUMENT", "SUBSTITUTES_WITH"})
        return relationships
