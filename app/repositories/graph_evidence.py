from __future__ import annotations

from typing import Any


def selected_entity_lookup(
    repo,
    entity_type: str | None = None,
    entity_id: str | None = None,
    entity_name: str | None = None,
) -> dict[str, Any] | None:
    resolved = repo.resolve_entity_reference(entity_type, entity_id)
    if not resolved and entity_id:
        resolved = repo._resolve_by_likely_label(entity_id)
    if not resolved and entity_name:
        resolved = repo._resolve_by_name(entity_name)
    if not resolved:
        return None
    return {
        "entity": resolved,
        "material": repo.get_material(resolved["id"]) if resolved["type"] == "material" else None,
        "supplier": repo.get_supplier(resolved["id"]) if resolved["type"] == "supplier" else None,
        "document": repo.document_detail(resolved["id"]) if resolved["type"] in {"document", "report"} else None,
        "component": repo.get_component(resolved["id"]) if resolved["type"] == "component" else None,
    }


def uploaded_record_lookup(
    repo,
    entity_type: str | None = None,
    entity_id: str | None = None,
    entity_name: str | None = None,
) -> dict[str, Any] | None:
    normalized_type = (entity_type or "").lower()
    if normalized_type == "component":
        component = repo.get_component(entity_id or "")
        return {"record_type": "component", "record": component} if component else None
    if normalized_type in {"document", "source", "source_document", "uploaded_record"}:
        document = repo.document_detail(entity_id or "")
        return {"record_type": "document", "record": document} if document else None
    if normalized_type in {"report", "test_report"}:
        report = repo.document_detail(entity_id or "")
        return {"record_type": "report", "record": report} if report else None
    if entity_id:
        document = repo.document_detail(entity_id)
        if document:
            record_type = "report" if document.get("report_id") else "document"
            return {"record_type": record_type, "record": document}
        component = repo.get_component(entity_id)
        if component:
            return {"record_type": "component", "record": component}
    if entity_name:
        name_lower = entity_name.lower()
        component = next((item for item in repo.runtime_components() if name_lower in item.get("name", "").lower()), None)
        if component:
            return {"record_type": "component", "record": repo.get_component(component["component_id"])}
    return None


def evidence_for_material(repo, material_id: str) -> dict[str, Any]:
    material = repo.material_index.get(material_id)
    if not material:
        return {}
    docs = [
        doc for doc in repo.all_documents()
        if doc.get("document_id") in material["source_document_ids"] or doc.get("material_id") == material_id
    ]
    reports = [report for report in repo.all_test_reports() if report.get("material_id") == material_id]
    return {"material": material, "documents": docs, "test_reports": reports}


def search_documents(repo, query: str, material_id: str | None = None) -> list[dict[str, Any]]:
    query_lower = query.lower()
    documents = repo.all_documents()
    reports = repo.all_test_reports()
    if material_id:
        documents = [item for item in documents if item.get("material_id") == material_id]
        reports = [item for item in reports if item.get("material_id") == material_id]
    results = []
    for document in documents:
        haystack = " ".join(
            [
                document.get("title", ""),
                document.get("document_type", ""),
                document.get("supplier_id", ""),
                document.get("extraction_summary", ""),
                " ".join(document.get("detected_terms", [])),
            ]
        ).lower()
        if query_lower in haystack:
            results.append({"type": "document", **document})
    for report in reports:
        haystack = " ".join(
            [
                report.get("title", ""),
                report.get("lab", ""),
                report.get("migration_status", ""),
                report.get("extraction_summary", ""),
                " ".join(report.get("detected_terms", [])),
            ]
        ).lower()
        if query_lower in haystack:
            results.append({"type": "test_report", **report})
    return results[:20]
