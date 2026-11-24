from __future__ import annotations

from typing import Any


def global_search(repo, query: str) -> list[dict[str, Any]]:
    query_lower = query.lower().strip()
    if not query_lower:
        return []
    results: list[dict[str, Any]] = []

    for material in repo.materials:
        haystack = " ".join(
            [
                material["name"],
                material["category"],
                material["descriptor"],
                material["composition"],
                " ".join(material["compliance_flags"]),
            ]
        ).lower()
        if query_lower in haystack:
            results.append(
                {
                    "entity_type": "material",
                    "entity_id": material["material_id"],
                    "title": material["name"],
                    "subtitle": f"{material['category']} | {material['compliance_state']}",
                    "meta": f"Sustainability {material['sustainability_score']} | Recyclability {material['recyclability_score']}",
                }
            )

    for product in repo.products:
        haystack = " ".join(
            [
                product["name"],
                product["industry_name"],
                product["application_name"],
                " ".join(product["buyer_names"]),
            ]
        ).lower()
        if query_lower in haystack:
            results.append(
                {
                    "entity_type": "product",
                    "entity_id": product["product_id"],
                    "title": product["name"],
                    "subtitle": f"{product['industry_name']} | {product['application_name']}",
                    "meta": f"Match {product['match_score']} | Sustainability {product['sustainability_score']}",
                }
            )

    for supplier in repo.suppliers:
        haystack = " ".join(
            [
                supplier["name"],
                supplier["country"],
                " ".join(supplier["regions_served"]),
                " ".join(supplier["certifications"]),
            ]
        ).lower()
        if query_lower in haystack:
            results.append(
                {
                    "entity_type": "supplier",
                    "entity_id": supplier["supplier_id"],
                    "title": supplier["name"],
                    "subtitle": f"{supplier['country']} | lead time {supplier['lead_time_days']} days",
                    "meta": f"Risk {supplier['disruption_risk_score']} | ESG {supplier['esg_score']}",
                }
            )

    for regulation in repo.regulations:
        haystack = " ".join(
            [
                regulation["name"],
                regulation["focus"],
                regulation["effective_date"],
            ]
        ).lower()
        if query_lower in haystack:
            results.append(
                {
                    "entity_type": "regulation",
                    "entity_id": regulation["regulation_id"],
                    "title": regulation["name"],
                    "subtitle": f"{'Active' if regulation['active'] else 'Upcoming'} | {regulation['effective_date']}",
                    "meta": f"Focus {regulation['focus']}",
                }
            )

    for document in repo.all_documents():
        haystack = " ".join(
            [
                document.get("title", ""),
                document.get("document_type", ""),
                document.get("extraction_summary", ""),
                " ".join(document.get("detected_terms", [])),
            ]
        ).lower()
        if query_lower in haystack:
            results.append(
                {
                    "entity_type": "document",
                    "entity_id": document.get("document_id", ""),
                    "title": document.get("title", "Document"),
                    "subtitle": f"{document.get('document_type', 'document')} | {document.get('issued_on', 'unknown')}",
                    "meta": document.get("extraction_summary", "Evidence source"),
                }
            )

    for report in repo.all_test_reports():
        haystack = " ".join(
            [
                report.get("title", ""),
                report.get("lab", ""),
                report.get("migration_status", ""),
                report.get("extraction_summary", ""),
            ]
        ).lower()
        if query_lower in haystack:
            results.append(
                {
                    "entity_type": "report",
                    "entity_id": report.get("report_id", ""),
                    "title": report.get("title", "Report"),
                    "subtitle": f"{report.get('lab', 'Uploaded source')} | {report.get('test_date', 'unknown')}",
                    "meta": report.get("migration_status", "Test report"),
                }
            )

    for component in repo.runtime_components():
        haystack = " ".join(
            [
                component.get("name", ""),
                component.get("summary", ""),
                " ".join(component.get("aliases", [])),
                " ".join(component.get("tags", [])),
            ]
        ).lower()
        if query_lower in haystack:
            results.append(
                {
                    "entity_type": "component",
                    "entity_id": component.get("component_id", ""),
                    "title": component.get("name", "Discovered component"),
                    "subtitle": f"{component.get('component_type', 'Web-discovered component')} | cached on {component.get('discovered_at', 'unknown date')}",
                    "meta": f"Stored from {component.get('source_name', 'web discovery')} for future lookups.",
                    "source_url": component.get("source_url", ""),
                    "discovery_state": "cached",
                }
            )

    return results[:28]
