from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
from datetime import datetime, timezone
import json
from statistics import mean
from typing import Any

from app.core.config import get_settings
from app.repositories.data_store import get_data_store


class LocalGraphRepository:
    def __init__(self) -> None:
        self.settings = get_settings()
        bundle = get_data_store().load_bundle()
        self.bundle = bundle
        self.materials = bundle["materials"]
        self.suppliers = bundle["suppliers"]
        self.applications = bundle["applications"]
        self.material_news = bundle["material_news"]
        self.regulations = bundle["regulations"]
        self.certifications = bundle["certifications"]
        self.recycling_streams = bundle["recycling_streams"]
        self.regions = bundle["regions"]
        self.industries = bundle["industries"]
        self.documents = bundle["source_documents"]
        self.test_reports = bundle["test_reports"]
        self.snapshots = bundle["quarterly_snapshots"]
        self.relationships = bundle["relationships"]
        self.manifest = bundle["manifest"]
        self.material_index = {item["material_id"]: item for item in self.materials}
        self.supplier_index = {item["supplier_id"]: item for item in self.suppliers}
        self.application_index = {item["application_id"]: item for item in self.applications}
        self.regulation_index = {item["regulation_id"]: item for item in self.regulations}
        self.news_index = {item["news_id"]: item for item in self.material_news}
        self.document_index = {item["document_id"]: item for item in self.documents}
        self.snapshots_by_supplier = defaultdict(list)
        self.snapshots_by_material = defaultdict(list)
        self.relationships_by_node = defaultdict(list)
        for snapshot in self.snapshots:
            self.snapshots_by_supplier[snapshot["supplier_id"]].append(snapshot)
            self.snapshots_by_material[snapshot["material_id"]].append(snapshot)
        for relationship in self.relationships:
            self.relationships_by_node[relationship["from"]].append(relationship)
            self.relationships_by_node[relationship["to"]].append(relationship)
        self.runtime_documents_path = self.settings.packgraph_runtime_dir / "uploaded_source_documents.json"
        self.runtime_test_reports_path = self.settings.packgraph_runtime_dir / "uploaded_test_reports.json"

    def _read_runtime_json(self, path, default):
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def runtime_documents(self) -> list[dict[str, Any]]:
        return self._read_runtime_json(self.runtime_documents_path, [])

    def runtime_test_reports(self) -> list[dict[str, Any]]:
        return self._read_runtime_json(self.runtime_test_reports_path, [])

    def all_documents(self) -> list[dict[str, Any]]:
        return [*self.documents, *self.runtime_documents()]

    def all_test_reports(self) -> list[dict[str, Any]]:
        return [*self.test_reports, *self.runtime_test_reports()]

    def list_materials(self) -> list[dict[str, Any]]:
        return self.materials

    def filter_materials(
        self,
        region: str | None = None,
        category: str | None = None,
        compliance_state: str | None = None,
        min_sustainability: int | None = None,
        search: str | None = None,
        material_family: str | None = None,
        regulation_id: str | None = None,
        claim_type: str | None = None,
        performance_metric: str | None = None,
        min_performance_score: int | None = None,
        supplier_capability: str | None = None,
    ) -> list[dict[str, Any]]:
        materials = self.materials
        if region:
            materials = [item for item in materials if region in item["regions_available"]]
        if category:
            materials = [item for item in materials if item["category"].lower() == category.lower()]
        if compliance_state:
            materials = [item for item in materials if item["compliance_state"].lower() == compliance_state.lower()]
        if min_sustainability is not None:
            materials = [item for item in materials if item["sustainability_score"] >= min_sustainability]
        if search:
            query = search.lower()
            materials = [item for item in materials if query in item["name"].lower() or query in item["composition"].lower()]
        if material_family:
            family = material_family.lower()
            materials = [
                item for item in materials
                if family in item["category"].lower()
                or family in item["descriptor"].lower()
                or family in item["composition"].lower()
            ]
        if regulation_id:
            materials = [item for item in materials if self._relationship_between(item["material_id"], regulation_id)]
        if claim_type:
            materials = [item for item in materials if self._matches_claim_type(item, claim_type)]
        if performance_metric and min_performance_score is not None:
            materials = [
                item for item in materials
                if int(item.get(performance_metric, 0)) >= int(min_performance_score)
            ]
        if supplier_capability:
            materials = [
                item for item in materials
                if any(self._supplier_supports_capability(self.supplier_index.get(supplier_id), supplier_capability) for supplier_id in item["supplier_ids"])
            ]
        return materials

    def get_material(self, material_id: str) -> dict[str, Any] | None:
        material = self.material_index.get(material_id)
        if not material:
            return None
        result = deepcopy(material)
        result["suppliers"] = [self.supplier_index[sid] for sid in material["supplier_ids"] if sid in self.supplier_index]
        result["snapshots"] = self.snapshots_by_material.get(material_id, [])
        result["documents"] = [
            doc for doc in self.all_documents()
            if doc.get("document_id") in material["source_document_ids"] or doc.get("material_id") == material_id
        ]
        result["test_reports"] = [report for report in self.all_test_reports() if report.get("material_id") == material_id]
        return result

    def list_suppliers(self) -> list[dict[str, Any]]:
        return self.suppliers

    def list_applications(self) -> list[dict[str, Any]]:
        return self.applications

    def list_news(self) -> list[dict[str, Any]]:
        return self.material_news

    def explore_entities(
        self,
        tab: str = "materials",
        search: str | None = None,
        category: str | None = None,
        supplier_id: str | None = None,
        application_id: str | None = None,
        compliance_state: str | None = None,
        min_sustainability: int | None = None,
    ) -> list[dict[str, Any]]:
        search_lower = search.lower().strip() if search else ""
        if tab == "applications":
            results = []
            for application in self.applications:
                linked_materials = self._materials_for_application(application["application_id"])
                if not linked_materials:
                    continue
                if category and not any(item["category"].lower() == category.lower() for item in linked_materials):
                    continue
                if supplier_id and not any(supplier_id in item["supplier_ids"] for item in linked_materials):
                    continue
                if compliance_state and not any(item["compliance_state"].lower() == compliance_state.lower() for item in linked_materials):
                    continue
                if min_sustainability is not None and max(item["sustainability_score"] for item in linked_materials) < min_sustainability:
                    continue
                haystack = " ".join([application["name"], application["use_case"], application["priority"]]).lower()
                if search_lower and search_lower not in haystack and not any(search_lower in item["name"].lower() for item in linked_materials):
                    continue
                linked_suppliers = self._suppliers_for_materials(linked_materials)
                results.append(
                    {
                        "entity_type": "application",
                        "entity_id": application["application_id"],
                        "title": application["name"],
                        "subtitle": f"{application['use_case']} | priority {application['priority']}",
                        "meta": f"{len(linked_materials)} materials | {len(linked_suppliers)} suppliers",
                        "tags": list(dict.fromkeys(item["category"] for item in linked_materials))[:3],
                        "focus_material_id": linked_materials[0]["material_id"],
                        "dashboard_prompt": f"What materials look best for the application {application['name']} and why?",
                    }
                )
            return results[:36]

        if tab == "suppliers":
            results = []
            for supplier in self.suppliers:
                supplied_materials = [self.material_index[item] for item in supplier["supplied_material_ids"] if item in self.material_index]
                if category and not any(item["category"].lower() == category.lower() for item in supplied_materials):
                    continue
                if application_id and not any(application_id in item["target_applications"] for item in supplied_materials):
                    continue
                if compliance_state and not any(item["compliance_state"].lower() == compliance_state.lower() for item in supplied_materials):
                    continue
                if min_sustainability is not None and max((item["sustainability_score"] for item in supplied_materials), default=0) < min_sustainability:
                    continue
                haystack = " ".join([supplier["name"], supplier["country"], " ".join(supplier["regions_served"])]).lower()
                if search_lower and search_lower not in haystack:
                    continue
                results.append(
                    {
                        "entity_type": "supplier",
                        "entity_id": supplier["supplier_id"],
                        "title": supplier["name"],
                        "subtitle": f"{supplier['country']} | lead time {supplier['lead_time_days']} days",
                        "meta": f"Risk {supplier['disruption_risk_score']} | {len(supplied_materials)} materials",
                        "tags": supplier["certifications"][:3],
                        "focus_material_id": supplied_materials[0]["material_id"] if supplied_materials else None,
                        "dashboard_prompt": f"Which risks and substitution options should I inspect for supplier {supplier['name']}?",
                    }
                )
            return results[:36]

        if tab == "news":
            results = []
            for item in self.material_news:
                linked_materials = [self.material_index[mid] for mid in item["related_material_ids"] if mid in self.material_index]
                if category and not any(material["category"].lower() == category.lower() for material in linked_materials):
                    continue
                if supplier_id and supplier_id not in item["related_supplier_ids"]:
                    continue
                if application_id and application_id not in item["related_application_ids"]:
                    continue
                if compliance_state and item["compliance_state"].lower() != compliance_state.lower():
                    continue
                if min_sustainability is not None and item["sustainability_score"] < min_sustainability:
                    continue
                haystack = " ".join([item["title"], item["summary"], item["topic"], item["source"]]).lower()
                if search_lower and search_lower not in haystack:
                    continue
                results.append(
                    {
                        "entity_type": "news",
                        "entity_id": item["news_id"],
                        "title": item["title"],
                        "subtitle": f"{item['source']} | {item['published_on']}",
                        "meta": f"{item['topic']} | sustainability {item['sustainability_score']}",
                        "tags": [item["topic"], item["source_type"], item["compliance_state"]],
                        "focus_material_id": item["related_material_ids"][0] if item["related_material_ids"] else None,
                        "dashboard_prompt": f"Explain the graph impact of this update: {item['title']}",
                    }
                )
            return results[:36]

        results = []
        for material in self.filter_materials(
            category=category,
            compliance_state=compliance_state,
            min_sustainability=min_sustainability,
            search=search,
        ):
            if supplier_id and supplier_id not in material["supplier_ids"]:
                continue
            if application_id and application_id not in material["target_applications"]:
                continue
            results.append(
                {
                    "entity_type": "material",
                    "entity_id": material["material_id"],
                    "title": material["name"],
                    "subtitle": f"{material['category']} | {material['compliance_state']}",
                    "meta": f"Sustainability {material['sustainability_score']} | Recyclability {material['recyclability_score']}",
                    "tags": [material["descriptor"], *material["regions_available"][:2]],
                    "focus_material_id": material["material_id"],
                    "dashboard_prompt": f"Map the strongest evidence, risks, and substitutes for {material['name']}.",
                }
            )
        return results[:36]

    def explore_detail(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        if entity_type == "material":
            material = self.get_material(entity_id)
            if not material:
                return None
            applications = [self.application_index[item] for item in material["target_applications"] if item in self.application_index]
            return {
                "entity_type": "material",
                "entity_id": material["material_id"],
                "title": material["name"],
                "summary": f"{material['descriptor']} {material['category']} used across {len(applications)} target applications.",
                "facts": [
                    {"label": "Composition", "value": material["composition"]},
                    {"label": "Compliance", "value": material["compliance_state"]},
                    {"label": "Sustainability", "value": material["sustainability_score"]},
                    {"label": "Food contact", "value": "Approved" if material["food_contact_safe"] else "Review required"},
                ],
                "related": {
                    "suppliers": [item["name"] for item in material["suppliers"][:4]],
                    "applications": [item["name"] for item in applications[:4]],
                    "documents": [item["title"] for item in material["documents"][:3]],
                },
                "focus_material_id": material["material_id"],
                "dashboard_prompt": f"Trace the graph evidence, supplier risk, and substitute logic for {material['name']}.",
            }

        if entity_type == "application":
            application = self.application_index.get(entity_id)
            if not application:
                return None
            linked_materials = self._materials_for_application(entity_id)
            linked_suppliers = self._suppliers_for_materials(linked_materials)
            return {
                "entity_type": "application",
                "entity_id": application["application_id"],
                "title": application["name"],
                "summary": f"{application['use_case']} workflow with {len(linked_materials)} linked material options and {len(linked_suppliers)} suppliers.",
                "facts": [
                    {"label": "Use case", "value": application["use_case"]},
                    {"label": "Priority", "value": application["priority"]},
                    {"label": "Material options", "value": len(linked_materials)},
                    {"label": "Supplier options", "value": len(linked_suppliers)},
                ],
                "related": {
                    "materials": [item["name"] for item in linked_materials[:4]],
                    "suppliers": [item["name"] for item in linked_suppliers[:4]],
                    "signals": [f"Average sustainability {round(mean(item['sustainability_score'] for item in linked_materials), 1)}"] if linked_materials else [],
                },
                "focus_material_id": linked_materials[0]["material_id"] if linked_materials else None,
                "dashboard_prompt": f"Recommend the best material paths for application {application['name']} and explain the tradeoffs.",
            }

        if entity_type == "supplier":
            supplier = self.get_supplier(entity_id)
            if not supplier:
                return None
            return {
                "entity_type": "supplier",
                "entity_id": supplier["supplier_id"],
                "title": supplier["name"],
                "summary": f"{supplier['country']} supplier supporting {len(supplier['supplied_materials'])} linked materials in the demo graph.",
                "facts": [
                    {"label": "Lead time", "value": f"{supplier['lead_time_days']} days"},
                    {"label": "Risk", "value": supplier["disruption_risk_score"]},
                    {"label": "ESG", "value": supplier["esg_score"]},
                    {"label": "Certifications", "value": len(supplier["certifications"])},
                ],
                "related": {
                    "materials": [item["name"] for item in supplier["supplied_materials"][:4]],
                    "certifications": supplier["certifications"][:4],
                    "regions": supplier["regions_served"][:4],
                },
                "focus_material_id": supplier["supplied_materials"][0]["material_id"] if supplier["supplied_materials"] else None,
                "dashboard_prompt": f"Inspect the sourcing risk, evidence coverage, and substitute options around supplier {supplier['name']}.",
            }

        if entity_type == "news":
            item = self.news_index.get(entity_id)
            if not item:
                return None
            related_materials = [self.material_index[mid]["name"] for mid in item["related_material_ids"] if mid in self.material_index]
            related_suppliers = [self.supplier_index[sid]["name"] for sid in item["related_supplier_ids"] if sid in self.supplier_index]
            related_applications = [self.application_index[aid]["name"] for aid in item["related_application_ids"] if aid in self.application_index]
            return {
                "entity_type": "news",
                "entity_id": item["news_id"],
                "title": item["title"],
                "summary": item["summary"],
                "facts": [
                    {"label": "Source", "value": item["source"]},
                    {"label": "Published", "value": item["published_on"]},
                    {"label": "Topic", "value": item["topic"]},
                    {"label": "Compliance state", "value": item["compliance_state"]},
                ],
                "related": {
                    "materials": related_materials[:4],
                    "suppliers": related_suppliers[:4],
                    "applications": related_applications[:4],
                },
                "focus_material_id": item["related_material_ids"][0] if item["related_material_ids"] else None,
                "dashboard_prompt": f"Summarize the graph impact of the update titled '{item['title']}'.",
            }
        return None

    def list_regulations(self) -> list[dict[str, Any]]:
        return self.regulations

    def global_search(self, query: str) -> list[dict[str, Any]]:
        query_lower = query.lower().strip()
        if not query_lower:
            return []
        results = []

        for material in self.materials:
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

        for supplier in self.suppliers:
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

        for regulation in self.regulations:
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

        for document in self.all_documents():
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

        for report in self.all_test_reports():
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

        return results[:28]

    def get_supplier(self, supplier_id: str) -> dict[str, Any] | None:
        supplier = self.supplier_index.get(supplier_id)
        if not supplier:
            return None
        snapshots = sorted(self.snapshots_by_supplier.get(supplier_id, []), key=lambda item: item["quarter"])
        materials = [self.material_index[item] for item in supplier["supplied_material_ids"] if item in self.material_index]
        current = snapshots[-1] if snapshots else None
        return {
            **deepcopy(supplier),
            "supplied_materials": materials,
            "certifications_detail": [
                {"name": certification, "status": "active", "coverage": supplier["country"]}
                for certification in supplier.get("certifications", [])
            ],
            "risk_trend": [
                {"quarter": item["quarter"], "risk_score": item["risk_score"], "compliance_score": item["compliance_score"]}
                for item in snapshots[-6:]
            ],
            "lead_time_trend": [
                {"quarter": item["quarter"], "lead_time_days": item["lead_time_days"], "price_index": item["price_index"]}
                for item in snapshots[-6:]
            ],
            "latest_snapshot": current,
        }

    def get_regulation(self, regulation_id: str) -> dict[str, Any] | None:
        regulation = self.regulation_index.get(regulation_id)
        if not regulation:
            return None
        affected_materials = []
        evidence_gaps = []
        likely_actions = []
        for relationship in self.relationships:
            if relationship["type"] != "REVIEWED_UNDER":
                continue
            if regulation_id not in {relationship["from"], relationship["to"]}:
                continue
            material_id = relationship["from"] if relationship["from"] != regulation_id else relationship["to"]
            material = self.material_index.get(material_id)
            if not material:
                continue
            affected_materials.append(
                {
                    "material_id": material["material_id"],
                    "name": material["name"],
                    "compliance_state": material["compliance_state"],
                    "supplier_count": len(material["supplier_ids"]),
                }
            )
            evidence = self.evidence_for_material(material["material_id"])
            if not any(doc.get("document_type") == "declaration" for doc in evidence.get("documents", [])):
                evidence_gaps.append(f"{material['name']} is missing a declaration.")
            if not evidence.get("test_reports"):
                evidence_gaps.append(f"{material['name']} is missing a lab report.")
            if material["compliance_state"] != "compliant":
                likely_actions.append(f"Move {material['name']} into immediate compliance review.")

        return {
            **deepcopy(regulation),
            "affected_materials": affected_materials[:12],
            "evidence_gaps": evidence_gaps[:10],
            "likely_actions": list(dict.fromkeys(likely_actions))[:8] or [
                "Review linked material dossiers before the effective date.",
                "Refresh supplier declarations for exposed materials.",
            ],
        }

    def compare_suppliers(self, supplier_ids: list[str] | None = None) -> list[dict[str, Any]]:
        suppliers = self.suppliers if not supplier_ids else [self.supplier_index[sid] for sid in supplier_ids if sid in self.supplier_index]
        compared = []
        for supplier in suppliers:
            snapshots = self.snapshots_by_supplier.get(supplier["supplier_id"], [])
            compared.append(
                {
                    **supplier,
                    "average_cost_pressure": round(mean(item["price_index"] for item in snapshots), 2) if snapshots else None,
                    "average_compliance_rate": round(mean(item["compliance_score"] for item in snapshots), 2) if snapshots else None,
                    "latest_snapshot": snapshots[-1] if snapshots else None,
                }
            )
        return sorted(compared, key=lambda item: (-item["esg_score"], item["disruption_risk_score"], item["lead_time_days"]))

    def _materials_for_application(self, application_id: str) -> list[dict[str, Any]]:
        return [item for item in self.materials if application_id in item["target_applications"]]

    def _suppliers_for_materials(self, materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
        supplier_ids = []
        for material in materials:
            supplier_ids.extend(material["supplier_ids"])
        unique = list(dict.fromkeys(supplier_ids))
        return [self.supplier_index[item] for item in unique if item in self.supplier_index]

    def recommend_food_packaging(self, prioritize_sustainability: bool = False) -> list[dict[str, Any]]:
        candidates = []
        for material in self.materials:
            if not material["food_contact_safe"]:
                continue
            if "food-contact-watch" in material["compliance_flags"]:
                continue
            score = (
                material["oxygen_barrier"]
                + material["moisture_barrier"]
                + material["seal_strength"]
                + material["recyclability_score"]
                + material["sustainability_score"]
            )
            if prioritize_sustainability:
                score += material["compostability_score"] * 1.25
                score -= material["cost_range"]["high"] * 0.15
            candidates.append(
                {
                    "material_id": material["material_id"],
                    "name": material["name"],
                    "category": material["category"],
                    "score": round(score, 2),
                    "applications": material["target_applications"],
                    "recyclability_score": material["recyclability_score"],
                    "sustainability_score": material["sustainability_score"],
                }
            )
        return sorted(candidates, key=lambda item: item["score"], reverse=True)[:10]

    def find_recyclable_substitutes(self, material_id: str) -> list[dict[str, Any]]:
        material = self.material_index.get(material_id)
        if not material:
            return []
        substitutes = []
        for sub_id in material["substitute_material_ids"]:
            substitute = self.material_index.get(sub_id)
            if substitute and substitute["recyclability_score"] >= material["recyclability_score"]:
                substitutes.append(substitute)
        return substitutes

    def non_compliant_materials(self, regulation_id: str) -> list[dict[str, Any]]:
        regulation = self.regulation_index.get(regulation_id)
        if not regulation:
            return []
        affected = []
        for material in self.materials:
            if regulation["focus"] in material["category"].lower() or regulation["focus"] in " ".join(material["compliance_flags"]).lower():
                if material["compliance_state"] != "compliant":
                    affected.append(material)
        return affected

    def evidence_for_material(self, material_id: str) -> dict[str, Any]:
        material = self.material_index.get(material_id)
        if not material:
            return {}
        docs = [
            doc for doc in self.all_documents()
            if doc.get("document_id") in material["source_document_ids"] or doc.get("material_id") == material_id
        ]
        reports = [report for report in self.all_test_reports() if report.get("material_id") == material_id]
        return {"material": material, "documents": docs, "test_reports": reports}

    def relationship_preview(self, material_id: str | None = None) -> list[dict[str, Any]]:
        links = self.relationships
        if material_id:
            links = [rel for rel in links if rel["from"] == material_id or rel["to"] == material_id]
        return links[:80]

    def graph_subgraph(self, material_id: str) -> dict[str, Any]:
        material = self.material_index.get(material_id)
        if not material:
            return {"nodes": [], "edges": []}
        nodes: dict[str, dict[str, Any]] = {
            material_id: {"id": material_id, "label": material["name"], "type": "material"},
        }
        edges = []
        for relationship in self.relationship_preview(material_id):
            source = relationship["from"]
            target = relationship["to"]
            edges.append({"source": source, "target": target, "type": relationship["type"]})
            if source not in nodes:
                nodes[source] = self._node_descriptor(source)
            if target not in nodes:
                nodes[target] = self._node_descriptor(target)
        return {"nodes": list(nodes.values()), "edges": edges}

    def graph_path(self, source_id: str, target_id: str) -> dict[str, Any]:
        queue = [(source_id, [source_id])]
        seen = {source_id}
        while queue:
            current, path = queue.pop(0)
            if current == target_id:
                nodes = [self._node_descriptor(node_id) for node_id in path]
                edges = []
                for index in range(len(path) - 1):
                    edge = self._relationship_between(path[index], path[index + 1])
                    if edge:
                        edges.append({"source": edge["from"], "target": edge["to"], "type": edge["type"]})
                return {"path": nodes, "edges": edges}
            for relationship in self.relationships_by_node.get(current, []):
                neighbor = relationship["to"] if relationship["from"] == current else relationship["from"]
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return {"path": [], "edges": []}

    def graph_node_insight(self, node_id: str) -> dict[str, Any]:
        node = self._node_descriptor(node_id)
        relationships = self.relationships_by_node.get(node_id, [])
        relationship_counts = defaultdict(int)
        related = []
        seen_related = set()
        for relationship in relationships:
            relationship_counts[relationship["type"]] += 1
            other_id = relationship["to"] if relationship["from"] == node_id else relationship["from"]
            if other_id in seen_related:
                continue
            seen_related.add(other_id)
            related_node = self._node_descriptor(other_id)
            related.append(
                {
                    "id": related_node["id"],
                    "label": related_node["label"],
                    "type": related_node["type"],
                    "relationship": relationship["type"],
                }
            )

        insight = {
            "node": node,
            "summary": f"{node['label']} is connected to {len(related)} nearby nodes across {len(relationship_counts)} relationship types.",
            "metrics": [],
            "facts": [],
            "relationship_counts": [
                {"label": item_type.replace("_", " ").title(), "value": count}
                for item_type, count in sorted(relationship_counts.items(), key=lambda item: (-item[1], item[0]))
            ],
            "timeline": [],
            "related": related[:12],
        }

        if node["type"] == "material":
            material = self.material_index.get(node_id)
            if not material:
                return insight
            snapshots = self.snapshots_by_material.get(node_id, [])
            documents = [
                doc for doc in self.all_documents()
                if doc.get("document_id") in material["source_document_ids"] or doc.get("material_id") == node_id
            ]
            reports = [report for report in self.all_test_reports() if report.get("material_id") == node_id]
            insight["summary"] = (
                f"{material['name']} is a {material['category']} candidate with {len(material['supplier_ids'])} suppliers, "
                f"{len(material['target_applications'])} target applications, and {material['compliance_state']} compliance status."
            )
            insight["metrics"] = [
                {"label": "Sustainability", "value": material["sustainability_score"]},
                {"label": "Recyclability", "value": material["recyclability_score"]},
                {"label": "Qualified suppliers", "value": len(material["supplier_ids"])},
                {"label": "Documents", "value": len(documents)},
            ]
            insight["facts"] = [
                {"label": "Composition", "value": material["composition"]},
                {"label": "Compliance state", "value": material["compliance_state"].replace("-", " ").title()},
                {"label": "Food contact", "value": "Approved" if material["food_contact_safe"] else "Review required"},
                {
                    "label": "Cost range",
                    "value": f"{material['cost_range']['low']} to {material['cost_range']['high']} {material['cost_range']['currency']}",
                },
                {"label": "Substitutes", "value": len(material["substitute_material_ids"])},
                {"label": "Test reports", "value": len(reports)},
            ]
            insight["timeline"] = [
                {
                    "title": snapshot["quarter"],
                    "detail": f"{snapshot['price_usd_per_kg']} USD/kg | lead time {snapshot['lead_time_days']} days",
                    "meta": f"Risk {snapshot['risk_score']} | compliance {snapshot['compliance_state'].replace('-', ' ')}",
                }
                for snapshot in snapshots[-4:]
            ]
            return insight

        if node["type"] == "supplier":
            supplier = self.supplier_index.get(node_id)
            if not supplier:
                return insight
            snapshots = self.snapshots_by_supplier.get(node_id, [])
            latest = snapshots[-1] if snapshots else None
            insight["summary"] = (
                f"{supplier['name']} serves {len(set(supplier['regions_served']))} regions and supplies "
                f"{len(supplier['supplied_material_ids'])} materials."
            )
            insight["metrics"] = [
                {"label": "Supplied materials", "value": len(supplier["supplied_material_ids"])},
                {"label": "Risk score", "value": supplier["disruption_risk_score"]},
                {"label": "ESG score", "value": supplier["esg_score"]},
                {"label": "Lead time", "value": f"{supplier['lead_time_days']} days"},
            ]
            insight["facts"] = [
                {"label": "Country", "value": supplier["country"]},
                {"label": "Regions served", "value": ", ".join(sorted(set(supplier["regions_served"])))},
                {"label": "Certifications", "value": ", ".join(supplier["certifications"])},
                {"label": "Latest watch", "value": latest["regulation_watch"] if latest else "No snapshots"},
            ]
            insight["timeline"] = [
                {
                    "title": snapshot["quarter"],
                    "detail": f"Risk {snapshot['risk_score']} | price index {snapshot['price_index']}",
                    "meta": f"Compliance score {snapshot['compliance_score']} | lead time {snapshot['lead_time_days']} days",
                }
                for snapshot in snapshots[-4:]
            ]
            return insight

        if node["type"] == "regulation":
            regulation = self.regulation_index.get(node_id)
            if not regulation:
                return insight
            affected = self.non_compliant_materials(node_id)
            related_materials = [item for item in related if item["type"] == "material"]
            insight["summary"] = (
                f"{regulation['name']} is {'active' if regulation['active'] else 'upcoming'} and currently touches "
                f"{len(related_materials)} directly linked materials."
            )
            insight["metrics"] = [
                {"label": "Status", "value": "Active" if regulation["active"] else "Upcoming"},
                {"label": "Effective date", "value": regulation["effective_date"]},
                {"label": "Linked materials", "value": len(related_materials)},
                {"label": "Out-of-bounds", "value": len(affected)},
            ]
            insight["facts"] = [
                {"label": "Focus area", "value": regulation["focus"].replace("-", " ").title()},
                {"label": "Compliance pressure", "value": f"{len(affected)} non-compliant materials"},
            ]
            insight["timeline"] = [
                {
                    "title": regulation["effective_date"],
                    "detail": f"{regulation['name']} becomes {'active' if regulation['active'] else 'effective'}",
                    "meta": f"Focus: {regulation['focus']}",
                }
            ]
            return insight

        if node["type"] == "application":
            application = self.application_index.get(node_id)
            if not application:
                return insight
            related_materials = [item["id"] for item in related if item["type"] == "material"]
            linked_materials = [self.material_index[item_id] for item_id in related_materials if item_id in self.material_index]
            compliant = sum(1 for item in linked_materials if item["compliance_state"] == "compliant")
            insight["summary"] = (
                f"{application['name']} is a {application['priority']} priority application with "
                f"{len(linked_materials)} linked material options."
            )
            insight["metrics"] = [
                {"label": "Linked materials", "value": len(linked_materials)},
                {"label": "Compliant options", "value": compliant},
                {"label": "Priority", "value": application["priority"].title()},
                {"label": "Use case", "value": application["use_case"]},
            ]
            insight["facts"] = [
                {"label": "Use case", "value": application["use_case"]},
                {"label": "Priority axis", "value": application["priority"].title()},
                {"label": "Industry", "value": application["industry_id"]},
            ]
            return insight

        if node["type"] == "document":
            document = next((item for item in self.all_documents() if item.get("document_id") == node_id), None)
            if not document:
                return insight
            supplier = self.supplier_index.get(document["supplier_id"])
            material = self.material_index.get(document["material_id"])
            insight["summary"] = (
                f"{document['title']} is a {document['document_type']} linked to "
                f"{material['name'] if material else document['material_id']}."
            )
            insight["metrics"] = [
                {"label": "Provenance", "value": document["provenance_score"]},
                {"label": "Issued", "value": document["issued_on"]},
                {"label": "Supplier", "value": supplier["name"] if supplier else document["supplier_id"]},
                {"label": "Material", "value": material["name"] if material else document["material_id"]},
            ]
            insight["facts"] = [
                {"label": "Document type", "value": document["document_type"].title()},
                {"label": "Checksum", "value": document["checksum"]},
            ]
            return insight

        if node["type"] == "test_report":
            report = next((item for item in self.all_test_reports() if item.get("report_id") == node_id), None)
            if not report:
                return insight
            material = self.material_index.get(report.get("material_id"))
            insight["summary"] = (
                f"{report['title']} is a lab report linked to "
                f"{material['name'] if material else report.get('material_id', 'an unknown material')}."
            )
            insight["metrics"] = [
                {"label": "Lab", "value": report.get("lab", "Uploaded source")},
                {"label": "Migration", "value": report.get("migration_status", "review required")},
                {"label": "Test date", "value": report.get("test_date", "unknown")},
                {"label": "Material", "value": material["name"] if material else report.get("material_id", "unknown")},
            ]
            insight["facts"] = [
                {"label": "Source filename", "value": report.get("source_filename", "uploaded artifact")},
                {"label": "Extraction summary", "value": report.get("extraction_summary", "No extraction summary available")},
            ]
            return insight

        if node["type"] == "recycling_stream":
            stream = next((item for item in self.recycling_streams if item["stream_id"] == node_id), None)
            if not stream:
                return insight
            linked_materials = [item for item in related if item["type"] == "material"]
            insight["summary"] = (
                f"{stream['name']} accepts {', '.join(stream['accepted_categories'])} and is linked "
                f"to {len(linked_materials)} materials in this dataset."
            )
            insight["metrics"] = [
                {"label": "Accepted categories", "value": len(stream["accepted_categories"])},
                {"label": "Linked materials", "value": len(linked_materials)},
            ]
            insight["facts"] = [
                {"label": "Accepted categories", "value": ", ".join(stream["accepted_categories"])},
            ]
            return insight

        return insight

    def compare_materials(self, material_ids: list[str], weights: dict[str, float] | None = None) -> list[dict[str, Any]]:
        weights = weights or {}
        defaults = {
            "sustainability_score": 1.0,
            "recyclability_score": 0.9,
            "compostability_score": 0.8,
            "oxygen_barrier": 0.6,
            "moisture_barrier": 0.6,
            "cost_efficiency": 0.7,
        }
        defaults.update(weights)
        compared = []
        for material_id in material_ids:
            material = self.material_index.get(material_id)
            if not material:
                continue
            cost_efficiency = max(0.0, 100 - (material["cost_range"]["high"] * 12))
            weighted_score = (
                material["sustainability_score"] * defaults["sustainability_score"]
                + material["recyclability_score"] * defaults["recyclability_score"]
                + material["compostability_score"] * defaults["compostability_score"]
                + material["oxygen_barrier"] * defaults["oxygen_barrier"]
                + material["moisture_barrier"] * defaults["moisture_barrier"]
                + cost_efficiency * defaults["cost_efficiency"]
            )
            compared.append(
                {
                    "material_id": material_id,
                    "name": material["name"],
                    "category": material["category"],
                    "descriptor": material["descriptor"],
                    "composition": material["composition"],
                    "compliance_state": material["compliance_state"],
                    "supplier_count": len(material["supplier_ids"]),
                    "cost_range": material["cost_range"],
                    "weighted_score": round(weighted_score, 2),
                    "scores": {
                        "sustainability": material["sustainability_score"],
                        "recyclability": material["recyclability_score"],
                        "compostability": material["compostability_score"],
                        "oxygen_barrier": material["oxygen_barrier"],
                        "moisture_barrier": material["moisture_barrier"],
                        "cost_efficiency": round(cost_efficiency, 2),
                    },
                }
            )
        return sorted(compared, key=lambda item: item["weighted_score"], reverse=True)

    def search_documents(self, query: str, material_id: str | None = None) -> list[dict[str, Any]]:
        query_lower = query.lower()
        documents = self.all_documents()
        reports = self.all_test_reports()
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

    def alerts(self) -> list[dict[str, Any]]:
        alerts = []
        today = date.fromisoformat("2026-07-11")
        for supplier in self.suppliers:
            snapshots = self.snapshots_by_supplier.get(supplier["supplier_id"], [])
            if len(snapshots) >= 2:
                ordered = sorted(snapshots, key=lambda item: item["quarter"])
                if ordered[-1]["risk_score"] - ordered[-2]["risk_score"] >= 8:
                    alerts.append(
                        {
                            "severity": "high",
                            "category": "supplier_risk_spike",
                            "title": f"{supplier['name']} risk spike",
                            "detail": f"Risk score increased to {ordered[-1]['risk_score']} in {ordered[-1]['quarter']}.",
                        }
                    )
            for snapshot in snapshots[-2:]:
                expiry = date.fromisoformat(snapshot["certification_expiration"])
                if (expiry - today).days <= 180:
                    alerts.append(
                        {
                            "severity": "medium",
                            "category": "certification_expiry",
                            "title": f"{supplier['name']} certification nearing expiry",
                            "detail": f"{snapshot['certification_name']} expires on {snapshot['certification_expiration']}.",
                        }
                    )
                    break
        for regulation in self.regulations:
            if not regulation["active"]:
                effective = date.fromisoformat(regulation["effective_date"])
                if (effective - today).days <= 120:
                    alerts.append(
                        {
                            "severity": "medium",
                            "category": "regulation_change",
                            "title": f"{regulation['name']} activates soon",
                            "detail": f"Effective on {regulation['effective_date']}.",
                        }
                    )
        for material in self.materials:
            snapshots = sorted(self.snapshots_by_material.get(material["material_id"], []), key=lambda item: item["quarter"])
            if len(snapshots) >= 2:
                previous = snapshots[-2]
                latest = snapshots[-1]
                if previous["compliance_state"] != latest["compliance_state"]:
                    alerts.append(
                        {
                            "severity": "high" if latest["compliance_state"] == "non-compliant" else "medium",
                            "category": "compliance_change",
                            "title": f"{material['name']} compliance state changed",
                            "detail": f"State moved from {previous['compliance_state']} to {latest['compliance_state']} in {latest['quarter']}.",
                        }
                    )
                price_shift = latest["price_usd_per_kg"] - previous["price_usd_per_kg"]
                if price_shift >= 0.35:
                    alerts.append(
                        {
                            "severity": "medium",
                            "category": "cost_shift",
                            "title": f"{material['name']} cost increased",
                            "detail": f"Price moved from {previous['price_usd_per_kg']} to {latest['price_usd_per_kg']} USD/kg in {latest['quarter']}.",
                        }
                    )

            docs = [
                doc for doc in self.all_documents()
                if doc.get("document_id") in material["source_document_ids"] or doc.get("material_id") == material["material_id"]
            ]
            reports = [report for report in self.all_test_reports() if report.get("material_id") == material["material_id"]]
            has_declaration = any(doc.get("document_type") == "declaration" for doc in docs)
            if not has_declaration or not reports:
                missing_parts = []
                if not has_declaration:
                    missing_parts.append("declaration")
                if not reports:
                    missing_parts.append("lab report")
                alerts.append(
                    {
                        "severity": "medium",
                        "category": "missing_evidence",
                        "title": f"{material['name']} is missing evidence",
                        "detail": f"Missing {' and '.join(missing_parts)} for the current material dossier.",
                    }
                )
        return alerts[:14]

    def analytics_overview(self) -> dict[str, Any]:
        snapshots_by_quarter = defaultdict(list)
        for snapshot in self.snapshots:
            snapshots_by_quarter[snapshot["quarter"]].append(snapshot)
        cost_trends = []
        compliance_drift = []
        supplier_risk_trend = []
        for quarter, items in sorted(snapshots_by_quarter.items()):
            cost_trends.append(
                {
                    "quarter": quarter,
                    "average_price_usd_per_kg": round(mean(item["price_usd_per_kg"] for item in items), 2),
                    "average_lead_time_days": round(mean(item["lead_time_days"] for item in items), 1),
                }
            )
            compliance_drift.append(
                {
                    "quarter": quarter,
                    "watch_count": sum(1 for item in items if item["compliance_state"] == "watch"),
                    "non_compliant_count": sum(1 for item in items if item["compliance_state"] == "non-compliant"),
                }
            )
            supplier_risk_trend.append(
                {
                    "quarter": quarter,
                    "average_risk_score": round(mean(item["risk_score"] for item in items), 1),
                }
            )
        supplier_performance = self.compare_suppliers()[:8]
        return {
            "cost_trends": cost_trends,
            "compliance_drift": compliance_drift,
            "supplier_risk_trend": supplier_risk_trend,
            "supplier_performance": supplier_performance,
        }

    def material_export_payload(self, material_id: str) -> dict[str, Any] | None:
        material = self.get_material(material_id)
        if not material:
            return None
        suppliers = [self.supplier_index[sid] for sid in material["supplier_ids"] if sid in self.supplier_index]
        regulations = [
            self.regulation_index[rel["to"]]
            for rel in self.relationships
            if rel["from"] == material_id and rel["type"] == "REVIEWED_UNDER" and rel["to"] in self.regulation_index
        ]
        alerts = [item for item in self.alerts() if material["name"] in item["title"] or material["name"] in item["detail"]]
        return {
            "material": material,
            "suppliers": suppliers,
            "regulations": regulations,
            "documents": material["documents"],
            "test_reports": material["test_reports"],
            "alerts": alerts,
        }

    def supplier_snapshot(self, supplier_ids: list[str]) -> list[dict[str, Any]]:
        return self.compare_suppliers(supplier_ids)

    def benchmark_coverage(self, raw_benchmarks: dict[str, Any]) -> dict[str, Any]:
        query_notes = [
            {"query": "top_food_materials", "note": "Ranks food-safe materials by sustainability attributes."},
            {"query": "supplier_risk", "note": "Measures supplier disruption exposure across supplied materials."},
            {"query": "document_trace", "note": "Tests provenance joins from materials to source documents."},
        ]
        return {
            **raw_benchmarks,
            "query_plan_notes": [
                "Neo4j should favor indexed node lookups and directed relationship traversals for these workloads.",
                "Memgraph comparisons should focus on latency and result parity for traversal-heavy queries.",
                "Coverage can be expanded with pathfinding, filtered aggregations, and temporal snapshot joins.",
            ],
            "query_set": query_notes,
        }

    def materials_at_risk(self) -> list[dict[str, Any]]:
        risky = []
        for material in self.materials:
            supplier_scores = [self.supplier_index[sid]["disruption_risk_score"] for sid in material["supplier_ids"] if sid in self.supplier_index]
            avg_risk = mean(supplier_scores) if supplier_scores else 0
            if avg_risk >= 62:
                risky.append(
                    {
                        "material_id": material["material_id"],
                        "name": material["name"],
                        "supplier_risk_score": round(avg_risk, 2),
                        "substitute_material_ids": material["substitute_material_ids"],
                    }
                )
        return sorted(risky, key=lambda item: item["supplier_risk_score"], reverse=True)

    def timeline_for_material(self, material_id: str) -> list[dict[str, Any]]:
        return self.snapshots_by_material.get(material_id, [])

    def backend_status(self) -> list[dict[str, Any]]:
        settings = get_settings()
        return [
            {"backend": "local", "active": settings.graph_backend == "local", "mode": "json graph cache", "status": "ready"},
            {"backend": "neo4j", "active": settings.graph_backend == "neo4j", "mode": "primary graph database", "status": "configured"},
            {"backend": "memgraph", "active": settings.graph_backend == "memgraph", "mode": "benchmark target", "status": "optional"},
        ]

    def _node_descriptor(self, node_id: str) -> dict[str, Any]:
        if node_id in self.material_index:
            return {"id": node_id, "label": self.material_index[node_id]["name"], "type": "material"}
        if node_id in self.supplier_index:
            return {"id": node_id, "label": self.supplier_index[node_id]["name"], "type": "supplier"}
        if node_id in self.application_index:
            return {"id": node_id, "label": self.application_index[node_id]["name"], "type": "application"}
        if node_id in self.regulation_index:
            return {"id": node_id, "label": self.regulation_index[node_id]["name"], "type": "regulation"}
        if node_id in self.document_index:
            return {"id": node_id, "label": self.document_index[node_id]["title"], "type": "document"}
        runtime_document = next((item for item in self.runtime_documents() if item.get("document_id") == node_id), None)
        if runtime_document:
            return {"id": node_id, "label": runtime_document["title"], "type": "document"}
        test_report = next((item for item in self.all_test_reports() if item.get("report_id") == node_id), None)
        if test_report:
            return {"id": node_id, "label": test_report["title"], "type": "test_report"}
        stream = next((item for item in self.recycling_streams if item["stream_id"] == node_id), None)
        if stream:
            return {"id": node_id, "label": stream["name"], "type": "recycling_stream"}
        return {"id": node_id, "label": node_id, "type": "unknown"}

    def _relationship_between(self, source_id: str, target_id: str) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in self.relationships
                if (item["from"] == source_id and item["to"] == target_id) or (item["from"] == target_id and item["to"] == source_id)
            ),
            None,
        )

    def _matches_claim_type(self, material: dict[str, Any], claim_type: str) -> bool:
        claim = claim_type.lower()
        if claim == "food_contact":
            return material["food_contact_safe"]
        if claim == "recyclable":
            return material["recyclability_score"] >= 70
        if claim == "compostable":
            return material["compostability_score"] >= 65
        if claim == "high_barrier":
            return material["oxygen_barrier"] >= 80 or material["moisture_barrier"] >= 80
        if claim == "low_cost":
            return material["cost_range"]["high"] <= 4.0
        return False

    def _supplier_supports_capability(self, supplier: dict[str, Any] | None, capability: str) -> bool:
        if not supplier:
            return False
        capability_lower = capability.lower()
        return (
            capability_lower in supplier["country"].lower()
            or any(capability_lower in region.lower() for region in supplier["regions_served"])
            or any(capability_lower in cert.lower() for cert in supplier["certifications"])
        )


class Neo4jAdminRepository:
    def __init__(self, uri: str, username: str, password: str):
        from neo4j import GraphDatabase

        self.driver = GraphDatabase.driver(uri, auth=(username, password))

    def run(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]

    def close(self) -> None:
        self.driver.close()


class Neo4jGraphRepository(LocalGraphRepository):
    ID_KEYS = [
        "material_id",
        "supplier_id",
        "application_id",
        "regulation_id",
        "document_id",
        "stream_id",
        "report_id",
        "snapshot_id",
        "region_id",
        "industry_id",
        "certification_id",
    ]

    LABEL_TO_ID_KEY = {
        "Material": "material_id",
        "Supplier": "supplier_id",
        "Application": "application_id",
        "Regulation": "regulation_id",
        "SourceDocument": "document_id",
        "RecyclingStream": "stream_id",
        "TestReport": "report_id",
        "QuarterlySnapshot": "snapshot_id",
        "Region": "region_id",
        "Industry": "industry_id",
        "Certification": "certification_id",
    }

    LABEL_TO_TYPE = {
        "Material": "material",
        "Supplier": "supplier",
        "Application": "application",
        "Regulation": "regulation",
        "SourceDocument": "document",
        "RecyclingStream": "recycling_stream",
        "TestReport": "test_report",
        "QuarterlySnapshot": "snapshot",
        "Region": "region",
        "Industry": "industry",
        "Certification": "certification",
    }

    CONSTRAINTS = [
        "CREATE CONSTRAINT material_id IF NOT EXISTS FOR (m:Material) REQUIRE m.material_id IS UNIQUE",
        "CREATE CONSTRAINT supplier_id IF NOT EXISTS FOR (s:Supplier) REQUIRE s.supplier_id IS UNIQUE",
        "CREATE CONSTRAINT application_id IF NOT EXISTS FOR (a:Application) REQUIRE a.application_id IS UNIQUE",
        "CREATE CONSTRAINT regulation_id IF NOT EXISTS FOR (r:Regulation) REQUIRE r.regulation_id IS UNIQUE",
        "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:SourceDocument) REQUIRE d.document_id IS UNIQUE",
    ]

    def __init__(self, settings=None) -> None:
        super().__init__()
        from neo4j import GraphDatabase

        self.settings = settings or get_settings()
        self.driver = GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_username, self.settings.neo4j_password),
        )
        self.driver.verify_connectivity()
        self.audit_path = self.settings.packgraph_runtime_dir / "neo4j_query_audit.jsonl"
        if self.settings.neo4j_auto_ingest:
            self.sync_bundle_to_neo4j()

    def close(self) -> None:
        self.driver.close()

    def sync_bundle_to_neo4j(self) -> None:
        entity_map = {
            "materials": ("Material", "material_id"),
            "suppliers": ("Supplier", "supplier_id"),
            "applications": ("Application", "application_id"),
            "regulations": ("Regulation", "regulation_id"),
            "certifications": ("Certification", "certification_id"),
            "recycling_streams": ("RecyclingStream", "stream_id"),
            "regions": ("Region", "region_id"),
            "industries": ("Industry", "industry_id"),
            "source_documents": ("SourceDocument", "document_id"),
            "test_reports": ("TestReport", "report_id"),
            "quarterly_snapshots": ("QuarterlySnapshot", "snapshot_id"),
        }
        relation_queries = {
            "TARGETS_APPLICATION": """
                UNWIND $rows AS row
                MATCH (a:Material {material_id: row.from})
                MATCH (b:Application {application_id: row.to})
                MERGE (a)-[:TARGETS_APPLICATION]->(b)
            """,
            "SUPPLIED_BY": """
                UNWIND $rows AS row
                MATCH (a:Material {material_id: row.from})
                MATCH (b:Supplier {supplier_id: row.to})
                MERGE (a)-[:SUPPLIED_BY]->(b)
            """,
            "HAS_DOCUMENT": """
                UNWIND $rows AS row
                MATCH (a:Material {material_id: row.from})
                MATCH (b:SourceDocument {document_id: row.to})
                MERGE (a)-[:HAS_DOCUMENT]->(b)
            """,
            "SUBSTITUTES_WITH": """
                UNWIND $rows AS row
                MATCH (a:Material {material_id: row.from})
                MATCH (b:Material {material_id: row.to})
                MERGE (a)-[:SUBSTITUTES_WITH]->(b)
            """,
            "RECYCLES_INTO": """
                UNWIND $rows AS row
                MATCH (a:Material {material_id: row.from})
                MATCH (b:RecyclingStream {stream_id: row.to})
                MERGE (a)-[:RECYCLES_INTO]->(b)
            """,
            "REVIEWED_UNDER": """
                UNWIND $rows AS row
                MATCH (a:Material {material_id: row.from})
                MATCH (b:Regulation {regulation_id: row.to})
                MERGE (a)-[:REVIEWED_UNDER]->(b)
            """,
            "SUPPLIES": """
                UNWIND $rows AS row
                MATCH (a:Supplier {supplier_id: row.from})
                MATCH (b:Material {material_id: row.to})
                MERGE (a)-[:SUPPLIES]->(b)
            """,
        }
        with self.driver.session(database=self.settings.neo4j_database) as session:
            for query in self.CONSTRAINTS:
                session.run(query).consume()
            for key, (label, id_key) in entity_map.items():
                session.run(
                    f"""
                    UNWIND $rows AS row
                    MERGE (n:{label} {{{id_key}: row.{id_key}}})
                    SET n += row
                    """,
                    {"rows": [self._normalize_neo4j_properties(row) for row in self.bundle[key]]},
                ).consume()
            for rel_type, query in relation_queries.items():
                rows = [rel for rel in self.relationships if rel["type"] == rel_type]
                session.run(query, {"rows": rows}).consume()

    def ingest_uploaded_artifact(self, record: dict[str, Any], kind: str) -> None:
        with self.driver.session(database=self.settings.neo4j_database) as session:
            if kind == "test_report":
                session.run(
                    """
                    MERGE (r:TestReport {report_id: $report_id})
                    SET r += $props
                    WITH r
                    MATCH (m:Material {material_id: $material_id})
                    MERGE (m)-[:HAS_TEST_REPORT]->(r)
                    """,
                    {
                        "report_id": record["report_id"],
                        "material_id": record["material_id"],
                        "props": self._normalize_neo4j_properties(record),
                    },
                ).consume()
                return

            session.run(
                """
                MERGE (d:SourceDocument {document_id: $document_id})
                SET d += $props
                WITH d
                MATCH (m:Material {material_id: $material_id})
                MERGE (m)-[:HAS_DOCUMENT]->(d)
                """,
                {
                    "document_id": record["document_id"],
                    "material_id": record["material_id"],
                    "props": self._normalize_neo4j_properties(record),
                },
            ).consume()

    def relationship_preview(self, material_id: str | None = None) -> list[dict[str, Any]]:
        query = """
        MATCH (a)-[r]-(b)
        WHERE $material_id IS NULL
            OR a.material_id = $material_id
            OR b.material_id = $material_id
        RETURN labels(a)[0] AS from_label,
               properties(a) AS from_props,
               type(r) AS type,
               labels(b)[0] AS to_label,
               properties(b) AS to_props
        LIMIT 80
        """
        rows = self._run_graph_query("relationship_preview", query, {"material_id": material_id})
        preview = []
        for row in rows:
            preview.append(
                {
                    "from": self._extract_node_id(row["from_label"], row["from_props"]),
                    "to": self._extract_node_id(row["to_label"], row["to_props"]),
                    "type": row["type"],
                }
            )
        return preview

    def graph_subgraph(self, material_id: str) -> dict[str, Any]:
        query = """
        MATCH (m:Material {material_id: $material_id})-[r]-(n)
        RETURN labels(startNode(r))[0] AS source_label,
               properties(startNode(r)) AS source_props,
               labels(endNode(r))[0] AS target_label,
               properties(endNode(r)) AS target_props,
               type(r) AS type
        """
        rows = self._run_graph_query("graph_subgraph", query, {"material_id": material_id})
        nodes = {material_id: self._node_descriptor(material_id)}
        edges = []
        for row in rows:
            source = self._normalize_node(row["source_label"], row["source_props"])
            target = self._normalize_node(row["target_label"], row["target_props"])
            nodes[source["id"]] = source
            nodes[target["id"]] = target
            edges.append({"source": source["id"], "target": target["id"], "type": row["type"]})
        return {"nodes": list(nodes.values()), "edges": edges}

    def graph_path(self, source_id: str, target_id: str) -> dict[str, Any]:
        query = """
        MATCH (source)
        WHERE any(k IN $id_keys WHERE source[k] = $source_id)
        MATCH (target)
        WHERE any(k IN $id_keys WHERE target[k] = $target_id)
        MATCH p = shortestPath((source)-[*..6]-(target))
        RETURN [node IN nodes(p) | {label: labels(node)[0], props: properties(node)}] AS nodes,
               [rel IN relationships(p) | {
                    type: type(rel),
                    source_label: labels(startNode(rel))[0],
                    source_props: properties(startNode(rel)),
                    target_label: labels(endNode(rel))[0],
                    target_props: properties(endNode(rel))
               }] AS edges
        """
        rows = self._run_graph_query(
            "graph_path",
            query,
            {"source_id": source_id, "target_id": target_id, "id_keys": self.ID_KEYS},
        )
        if not rows:
            return {"path": [], "edges": []}
        row = rows[0]
        path = [self._normalize_node(item["label"], item["props"]) for item in row["nodes"]]
        edges = [
            {
                "source": self._extract_node_id(item["source_label"], item["source_props"]),
                "target": self._extract_node_id(item["target_label"], item["target_props"]),
                "type": item["type"],
            }
            for item in row["edges"]
        ]
        return {"path": path, "edges": edges}

    def graph_node_insight(self, node_id: str) -> dict[str, Any]:
        insight = super().graph_node_insight(node_id)
        query = """
        MATCH (node)
        WHERE any(k IN $id_keys WHERE node[k] = $node_id)
        OPTIONAL MATCH (node)-[r]-(other)
        RETURN type(r) AS relationship_type,
               labels(other)[0] AS other_label,
               properties(other) AS other_props
        """
        rows = self._run_graph_query("graph_node_insight", query, {"node_id": node_id, "id_keys": self.ID_KEYS})
        relationship_counts = defaultdict(int)
        related = []
        seen = set()
        for row in rows:
            rel_type = row.get("relationship_type")
            if not rel_type or not row.get("other_label") or row.get("other_props") is None:
                continue
            relationship_counts[rel_type] += 1
            node = self._normalize_node(row["other_label"], row["other_props"])
            if node["id"] in seen:
                continue
            seen.add(node["id"])
            related.append(
                {
                    "id": node["id"],
                    "label": node["label"],
                    "type": node["type"],
                    "relationship": rel_type,
                }
            )
        insight["relationship_counts"] = [
            {"label": item_type.replace("_", " ").title(), "value": count}
            for item_type, count in sorted(relationship_counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        insight["related"] = related[:12]
        return insight

    def backend_status(self) -> list[dict[str, Any]]:
        statuses = super().backend_status()
        for status in statuses:
            if status["backend"] == "neo4j":
                status["status"] = "ready"
        return statuses

    def _run_graph_query(self, query_name: str, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = parameters or {}
        with self.driver.session(database=self.settings.neo4j_database) as session:
            explain = session.run(f"EXPLAIN {query}", params)
            explain_summary = explain.consume()
            result = session.run(query, params)
            rows = [dict(record) for record in result]
            result_summary = result.consume()
        self._write_query_audit(
            query_name=query_name,
            query=query,
            parameters=params,
            result_count=len(rows),
            plan=self._serialize_plan(getattr(explain_summary, "plan", None)),
            counters=self._serialize_counters(getattr(result_summary, "counters", None)),
        )
        return rows

    def _write_query_audit(
        self,
        query_name: str,
        query: str,
        parameters: dict[str, Any],
        result_count: int,
        plan: dict[str, Any] | None,
        counters: dict[str, Any],
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query_name": query_name,
            "backend": "neo4j",
            "database": self.settings.neo4j_database,
            "result_count": result_count,
            "parameters": parameters,
            "query": " ".join(query.split()),
            "plan": plan,
            "counters": counters,
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def _serialize_plan(self, plan) -> dict[str, Any] | None:
        if not plan:
            return None
        children = getattr(plan, "children", None) or []
        return {
            "operator_type": getattr(plan, "operator_type", None),
            "arguments": getattr(plan, "arguments", {}),
            "identifiers": getattr(plan, "identifiers", []),
            "children": [self._serialize_plan(child) for child in children],
        }

    def _normalize_node(self, label: str, props: dict[str, Any]) -> dict[str, Any]:
        node_id = self._extract_node_id(label, props)
        node_type = self.LABEL_TO_TYPE.get(label, label.lower())
        id_key = self.LABEL_TO_ID_KEY.get(label, "")
        label_value = (
            props.get("name")
            or props.get("title")
            or props.get(id_key)
            or node_id
        )
        return {"id": node_id, "label": label_value, "type": node_type}

    def _extract_node_id(self, label: str, props: dict[str, Any]) -> str:
        id_key = self.LABEL_TO_ID_KEY.get(label)
        if id_key and props.get(id_key):
            return str(props[id_key])
        for key in self.ID_KEYS:
            if props.get(key):
                return str(props[key])
        return str(props.get("id", "unknown"))

    def _serialize_counters(self, counters) -> dict[str, Any]:
        if counters is None:
            return {}
        return {
            "contains_updates": getattr(counters, "contains_updates", False),
            "nodes_created": getattr(counters, "nodes_created", 0),
            "nodes_deleted": getattr(counters, "nodes_deleted", 0),
            "relationships_created": getattr(counters, "relationships_created", 0),
            "relationships_deleted": getattr(counters, "relationships_deleted", 0),
            "properties_set": getattr(counters, "properties_set", 0),
            "labels_added": getattr(counters, "labels_added", 0),
            "labels_removed": getattr(counters, "labels_removed", 0),
            "indexes_added": getattr(counters, "indexes_added", 0),
            "indexes_removed": getattr(counters, "indexes_removed", 0),
            "constraints_added": getattr(counters, "constraints_added", 0),
            "constraints_removed": getattr(counters, "constraints_removed", 0),
        }

    def _normalize_neo4j_properties(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = {}
        for key, value in row.items():
            if isinstance(value, dict):
                for nested_key, nested_value in self._flatten_nested_dict(value, prefix=key).items():
                    normalized[nested_key] = self._normalize_scalar_or_list(nested_value)
            else:
                normalized[key] = self._normalize_scalar_or_list(value)
        return normalized

    def _flatten_nested_dict(self, value: dict[str, Any], prefix: str) -> dict[str, Any]:
        flattened = {}
        for nested_key, nested_value in value.items():
            composite_key = f"{prefix}_{nested_key}"
            if isinstance(nested_value, dict):
                flattened.update(self._flatten_nested_dict(nested_value, composite_key))
            else:
                flattened[composite_key] = nested_value
        return flattened

    def _normalize_scalar_or_list(self, value: Any) -> Any:
        if isinstance(value, list):
            if all(isinstance(item, (str, int, float, bool)) or item is None for item in value):
                return value
            return json.dumps(value, sort_keys=True)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return json.dumps(value, sort_keys=True)


def build_graph_repository(settings=None) -> LocalGraphRepository:
    settings = settings or get_settings()
    if settings.graph_backend == "neo4j":
        try:
            return Neo4jGraphRepository(settings)
        except Exception:
            settings.graph_backend = "local"
            return LocalGraphRepository()
    return LocalGraphRepository()
