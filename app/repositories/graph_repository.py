from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
from datetime import datetime, timezone
import json
from statistics import mean
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.core.config import get_settings
from app.models.entities import (
    ApplicationRecord,
    MaterialRecord,
    NewsRecord,
    ProductRecord,
    QuarterlySnapshot,
    RegulationRecord,
    Relationship,
    SourceDocumentRecord,
    SupplierRecord,
    TestReportRecord,
)
from app.repositories.data_store import get_data_store
from app.repositories.graph_detail import explore_detail as run_explore_detail
from app.repositories.graph_detail import explore_entities as run_explore_entities
from app.repositories.graph_evidence import evidence_for_material as build_evidence_for_material
from app.repositories.graph_evidence import search_documents as run_document_search
from app.repositories.graph_evidence import selected_entity_lookup as resolve_selected_entity_lookup
from app.repositories.graph_evidence import uploaded_record_lookup as resolve_uploaded_record_lookup
from app.repositories.graph_health import backend_status as build_backend_status
from app.repositories.graph_health import graph_health as build_graph_health
from app.repositories.graph_materials import compare_materials as build_material_comparison
from app.repositories.graph_materials import get_material as load_material_detail
from app.repositories.graph_materials import materials_at_risk as build_material_risk_list
from app.repositories.graph_products import build_products as run_build_products
from app.repositories.graph_products import classify_material
from app.repositories.graph_products import materials_for_application
from app.repositories.graph_products import suppliers_for_materials
from app.repositories.graph_products import thumbnail_label
from app.repositories.graph_search import global_search as run_global_search
from app.repositories.graph_suppliers import compare_suppliers as build_supplier_comparison
from app.repositories.graph_suppliers import get_supplier as load_supplier_detail
from app.repositories.graph_traversal import graph_node_insight as build_graph_node_insight
from app.repositories.graph_traversal import graph_path as build_graph_path
from app.repositories.graph_traversal import graph_subgraph as build_graph_subgraph
from app.repositories.graph_traversal import relationship_preview as build_relationship_preview


class GraphRepositoryError(RuntimeError):
    """Base graph repository error with a user-safe message."""


class GraphConnectionError(GraphRepositoryError):
    """Raised when Neo4j connectivity is unavailable."""


class GraphQueryFailure(GraphRepositoryError):
    """Raised when a Neo4j query cannot be executed safely."""


def _safe_neo4j_uri(uri: str) -> str:
    parts = urlsplit(uri)
    if not parts.scheme or not parts.netloc:
        return uri
    host = parts.netloc.split("@")[-1]
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


class LocalGraphRepository:
    materials: list[MaterialRecord]
    suppliers: list[SupplierRecord]
    applications: list[ApplicationRecord]
    material_news: list[NewsRecord]
    regulations: list[RegulationRecord]
    documents: list[SourceDocumentRecord]
    test_reports: list[TestReportRecord]
    snapshots: list[QuarterlySnapshot]
    relationships: list[Relationship]
    products: list[ProductRecord]
    material_index: dict[str, MaterialRecord]
    supplier_index: dict[str, SupplierRecord]
    application_index: dict[str, ApplicationRecord]
    regulation_index: dict[str, RegulationRecord]
    news_index: dict[str, NewsRecord]
    document_index: dict[str, SourceDocumentRecord]
    product_index: dict[str, ProductRecord]

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
        self.industry_index = {item["industry_id"]: item for item in self.industries}
        self.snapshots_by_supplier = defaultdict(list)
        self.snapshots_by_material = defaultdict(list)
        self.relationships_by_node = defaultdict(list)
        for snapshot in self.snapshots:
            self.snapshots_by_supplier[snapshot["supplier_id"]].append(snapshot)
            self.snapshots_by_material[snapshot["material_id"]].append(snapshot)
        for relationship in self.relationships:
            self.relationships_by_node[relationship["from"]].append(relationship)
            self.relationships_by_node[relationship["to"]].append(relationship)
        self.runtime_components_path = self.settings.packgraph_runtime_dir / "discovered_components.json"
        self.runtime_documents_path = self.settings.packgraph_runtime_dir / "uploaded_source_documents.json"
        self.runtime_test_reports_path = self.settings.packgraph_runtime_dir / "uploaded_test_reports.json"
        self.products = run_build_products(self)
        self.product_index = {item["product_id"]: item for item in self.products}

    # -- Runtime JSON helpers -----------------------------------------------

    def _read_runtime_json(self, path, default):
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def runtime_documents(self) -> list[dict[str, Any]]:
        return self._read_runtime_json(self.runtime_documents_path, [])

    def runtime_test_reports(self) -> list[dict[str, Any]]:
        return self._read_runtime_json(self.runtime_test_reports_path, [])

    def runtime_components(self) -> list[dict[str, Any]]:
        return self._read_runtime_json(self.runtime_components_path, [])

    def all_documents(self) -> list[dict[str, Any]]:
        return [*self.documents, *self.runtime_documents()]

    def all_test_reports(self) -> list[dict[str, Any]]:
        return [*self.test_reports, *self.runtime_test_reports()]

    # -- List / filter / lookup ---------------------------------------------

    def list_components(self) -> list[dict[str, Any]]:
        return self.runtime_components()

    def get_component(self, component_id: str) -> dict[str, Any] | None:
        component = next((item for item in self.runtime_components() if item.get("component_id") == component_id), None)
        if not component:
            return None
        result = deepcopy(component)
        result["related_materials"] = [
            self.material_index[item]
            for item in component.get("related_material_ids", [])
            if item in self.material_index
        ]
        return result

    def list_materials(self) -> list[MaterialRecord]:
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
    ) -> list[MaterialRecord]:
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

    def get_material(self, material_id: str) -> MaterialRecord | None:
        return load_material_detail(self, material_id)

    def list_suppliers(self, region: str | None = None) -> list[SupplierRecord]:
        if not region:
            return self.suppliers
        region_lower = region.lower()
        return [
            item
            for item in self.suppliers
            if any(served.lower() == region_lower for served in item.get("regions_served", []))
        ]

    def supplier_region_summary(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = defaultdict(int)
        for supplier in self.suppliers:
            for region in supplier.get("regions_served", []):
                counts[region] += 1
        return [
            {"region": region, "supplier_count": supplier_count}
            for region, supplier_count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]

    def list_applications(self) -> list[ApplicationRecord]:
        return self.applications

    def list_products(self) -> list[ProductRecord]:
        return self.products

    def list_news(self) -> list[NewsRecord]:
        return self.material_news

    def explore_autocomplete(self, query: str) -> list[dict[str, Any]]:
        query_lower = query.lower().strip()
        if len(query_lower) < 2:
            return []
        suggestions: list[dict[str, Any]] = []
        for material in self.materials:
            if query_lower in material["name"].lower():
                suggestions.append({"entity_type": "material", "entity_id": material["material_id"], "label": material["name"]})
        for product in self.products:
            if query_lower in product["name"].lower():
                suggestions.append({"entity_type": "product", "entity_id": product["product_id"], "label": product["name"]})
        for supplier in self.suppliers:
            if query_lower in supplier["name"].lower():
                suggestions.append({"entity_type": "supplier", "entity_id": supplier["supplier_id"], "label": supplier["name"]})
        return suggestions[:8]

    def list_regulations(self) -> list[RegulationRecord]:
        return self.regulations

    def get_supplier(self, supplier_id: str) -> SupplierRecord | None:
        return load_supplier_detail(self, supplier_id)

    def get_regulation(self, regulation_id: str) -> RegulationRecord | None:
        regulation = self.regulation_index.get(regulation_id)
        if not regulation:
            return None
        affected_materials: list[dict[str, Any]] = []
        evidence_gaps: list[str] = []
        likely_actions: list[str] = []
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

    # -- Delegated explore / search / detail --------------------------------

    def explore_entities(
        self,
        tab: str = "materials",
        search: str | None = None,
        category: str | None = None,
        supplier_id: str | None = None,
        application_id: str | None = None,
        compliance_state: str | None = None,
        min_sustainability: int | None = None,
        region: str | None = None,
        taxonomy: str | None = None,
    ) -> list[dict[str, Any]]:
        return run_explore_entities(
            self, tab=tab, search=search, category=category, supplier_id=supplier_id,
            application_id=application_id, compliance_state=compliance_state,
            min_sustainability=min_sustainability, region=region, taxonomy=taxonomy,
        )

    def explore_detail(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        return run_explore_detail(self, entity_type, entity_id)

    def global_search(self, query: str) -> list[dict[str, Any]]:
        return run_global_search(self, query)

    # -- Entity resolution --------------------------------------------------

    def resolve_entity_reference(self, entity_type: str | None, entity_id: str | None) -> dict[str, Any] | None:
        if not entity_type or not entity_id:
            return None
        normalized_type = entity_type.lower()
        if normalized_type == "material" and entity_id in self.material_index:
            return {"type": "material", "id": entity_id, "label": self.material_index[entity_id]["name"]}
        if normalized_type == "supplier" and entity_id in self.supplier_index:
            return {"type": "supplier", "id": entity_id, "label": self.supplier_index[entity_id]["name"]}
        if normalized_type == "application" and entity_id in self.application_index:
            return {"type": "application", "id": entity_id, "label": self.application_index[entity_id]["name"]}
        if normalized_type == "regulation" and entity_id in self.regulation_index:
            return {"type": "regulation", "id": entity_id, "label": self.regulation_index[entity_id]["name"]}
        if normalized_type == "news" and entity_id in self.news_index:
            return {"type": "news", "id": entity_id, "label": self.news_index[entity_id]["title"]}
        if normalized_type == "component":
            component = self.get_component(entity_id)
            if component:
                return {"type": "component", "id": entity_id, "label": component.get("name", entity_id)}
        if normalized_type == "document":
            document = next((item for item in self.all_documents() if item.get("document_id") == entity_id), None)
            if document:
                return {"type": "document", "id": entity_id, "label": document.get("title", entity_id)}
        if normalized_type in {"report", "test_report"}:
            report = next((item for item in self.all_test_reports() if item.get("report_id") == entity_id), None)
            if report:
                return {"type": "report", "id": entity_id, "label": report.get("title", entity_id)}
        return None

    def validate_entity_reference(self, entity_type: str | None, entity_id: str | None) -> dict[str, Any]:
        resolved = self.resolve_entity_reference(entity_type, entity_id)
        return {
            "valid": resolved is not None,
            "entity": resolved,
            "message": "Reference resolved." if resolved else "Unknown or missing entity reference.",
        }

    def selected_material_lookup(self, material_id: str) -> dict[str, Any] | None:
        return self.get_material(material_id)

    def selected_supplier_lookup(self, supplier_id: str) -> dict[str, Any] | None:
        return self.get_supplier(supplier_id)

    def selected_entity_lookup(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        entity_name: str | None = None,
    ) -> dict[str, Any] | None:
        return resolve_selected_entity_lookup(self, entity_type, entity_id, entity_name)

    def uploaded_record_lookup(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        entity_name: str | None = None,
    ) -> dict[str, Any] | None:
        return resolve_uploaded_record_lookup(self, entity_type, entity_id, entity_name)

    def graph_health(self) -> dict[str, Any]:
        return build_graph_health(self)

    def _resolve_by_likely_label(self, entity_id: str) -> dict[str, Any] | None:
        prefix_map = {
            "MAT-": "material",
            "SUP-": "supplier",
            "APP-": "application",
            "REGU-": "regulation",
            "DOC-": "document",
            "REP-": "report",
            "PROD-": "product",
            "COMP-": "component",
        }
        for prefix, entity_type in prefix_map.items():
            if entity_id.startswith(prefix):
                return self.resolve_entity_reference(entity_type, entity_id)
        return None

    def _resolve_by_name(self, entity_name: str) -> dict[str, Any] | None:
        name_lower = entity_name.lower().strip()
        if not name_lower:
            return None
        collections = [
            ("material", self.materials, "material_id", "name"),
            ("supplier", self.suppliers, "supplier_id", "name"),
            ("application", self.applications, "application_id", "name"),
            ("regulation", self.regulations, "regulation_id", "name"),
        ]
        for entity_type, rows, id_key, label_key in collections:
            exact = next((item for item in rows if item.get(label_key, "").lower() == name_lower), None)
            if exact:
                return {"type": entity_type, "id": exact[id_key], "label": exact[label_key]}
        for entity_type, rows, id_key, label_key in collections:
            partial = next((item for item in rows if name_lower in item.get(label_key, "").lower()), None)
            if partial:
                return {"type": entity_type, "id": partial[id_key], "label": partial[label_key]}
        return None

    # -- Integrity / documents ----------------------------------------------

    def integrity_report(self) -> dict[str, Any]:
        missing_suppliers = [
            material["material_id"]
            for material in self.materials
            if any(supplier_id not in self.supplier_index for supplier_id in material.get("supplier_ids", []))
        ]
        missing_applications = [
            material["material_id"]
            for material in self.materials
            if any(application_id not in self.application_index for application_id in material.get("target_applications", []))
        ]
        dangling_relationships = [
            relationship
            for relationship in self.relationships
            if not self.resolve_entity_reference(self._type_from_node_id(relationship["from"]), relationship["from"])
            or not self.resolve_entity_reference(self._type_from_node_id(relationship["to"]), relationship["to"])
        ]
        return {
            "valid": not missing_suppliers and not missing_applications and not dangling_relationships,
            "checks": [
                {"label": "Material -> supplier links", "issues": len(missing_suppliers)},
                {"label": "Material -> application links", "issues": len(missing_applications)},
                {"label": "Graph relationship endpoints", "issues": len(dangling_relationships)},
            ],
            "samples": {
                "materials_missing_suppliers": missing_suppliers[:5],
                "materials_missing_applications": missing_applications[:5],
                "dangling_relationships": dangling_relationships[:5],
            },
        }

    def document_detail(self, document_id: str) -> dict[str, Any] | None:
        document = next((item for item in self.all_documents() if item.get("document_id") == document_id), None)
        if document:
            field_confidence = document.get("field_confidence", [])
            return {
                **document,
                "preview_text": document.get("extraction_summary") or "Synthetic document preview for the selected source.",
                "extracted_fields": [
                    {"label": "Document type", "value": document.get("document_type", "Unknown")},
                    {"label": "Issued on", "value": document.get("issued_on", "Unknown")},
                    {"label": "Provenance score", "value": document.get("provenance_score", "n/a")},
                ],
                "field_confidence": field_confidence,
                "confidence_summary": f"{round((document.get('extraction_confidence', 0) or 0) * 100)}%",
                "missing_fields": document.get("missing_fields", []),
                "pii_flags": document.get("pii_flags", []),
                "citation_spans": [document.get("extraction_summary")] if document.get("extraction_summary") else [],
            }
        report = next((item for item in self.all_test_reports() if item.get("report_id") == document_id), None)
        if report:
            field_confidence = report.get("field_confidence", [])
            return {
                **report,
                "preview_text": report.get("extraction_summary") or "Synthetic test report preview for the selected evidence.",
                "extracted_fields": [
                    {"label": "Lab", "value": report.get("lab", "Unknown")},
                    {"label": "Migration", "value": report.get("migration_status", "Unknown")},
                    {"label": "Test date", "value": report.get("test_date", "Unknown")},
                ],
                "field_confidence": field_confidence,
                "confidence_summary": f"{round((report.get('extraction_confidence', 0) or 0) * 100)}%",
                "missing_fields": report.get("missing_fields", []),
                "pii_flags": report.get("pii_flags", []),
                "citation_spans": [report.get("extraction_summary")] if report.get("extraction_summary") else [],
            }
        return None

    # -- Delegated graph / comparison / evidence ----------------------------

    def compare_suppliers(self, supplier_ids: list[str] | None = None) -> list[dict[str, Any]]:
        return build_supplier_comparison(self, supplier_ids)

    def recommend_food_packaging(self, prioritize_sustainability: bool = False) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
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
        substitutes: list[dict[str, Any]] = []
        for sub_id in material["substitute_material_ids"]:
            substitute = self.material_index.get(sub_id)
            if substitute and substitute["recyclability_score"] >= material["recyclability_score"]:
                substitutes.append(substitute)
        return substitutes

    def non_compliant_materials(self, regulation_id: str) -> list[dict[str, Any]]:
        regulation = self.regulation_index.get(regulation_id)
        if not regulation:
            return []
        affected: list[dict[str, Any]] = []
        for material in self.materials:
            if regulation["focus"] in material["category"].lower() or regulation["focus"] in " ".join(material["compliance_flags"]).lower():
                if material["compliance_state"] != "compliant":
                    affected.append(material)
        return affected

    def evidence_for_material(self, material_id: str) -> dict[str, Any]:
        return build_evidence_for_material(self, material_id)

    def relationship_preview(self, material_id: str | None = None) -> list[dict[str, Any]]:
        return build_relationship_preview(self, material_id)

    def graph_subgraph(self, material_id: str) -> dict[str, Any]:
        return build_graph_subgraph(self, material_id)

    def graph_path(self, source_id: str, target_id: str) -> dict[str, Any]:
        return build_graph_path(self, source_id, target_id)

    def graph_node_insight(self, node_id: str) -> dict[str, Any]:
        insight = build_graph_node_insight(self, node_id)
        node = insight["node"]
        related = insight["related"]

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
        return build_material_comparison(self, material_ids, weights)

    def search_documents(self, query: str, material_id: str | None = None) -> list[dict[str, Any]]:
        return run_document_search(self, query, material_id)

    # -- Alerts / analytics -------------------------------------------------

    def alerts(self) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
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
                missing_parts: list[str] = []
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
        snapshots_by_quarter: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for snapshot in self.snapshots:
            snapshots_by_quarter[snapshot["quarter"]].append(snapshot)
        cost_trends: list[dict[str, Any]] = []
        compliance_drift: list[dict[str, Any]] = []
        supplier_risk_trend: list[dict[str, Any]] = []
        material_adoption: list[dict[str, Any]] = []
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
            material_adoption.append(
                {
                    "quarter": quarter,
                    "adoption_count": sum(1 for item in items if item["compliance_state"] == "compliant"),
                }
            )
        supplier_performance = self.compare_suppliers()[:8]
        regulation_counts: dict[str, int] = defaultdict(int)
        for relationship in self.relationships:
            if relationship["type"] == "REVIEWED_UNDER":
                regulation_id = relationship["to"] if relationship["to"].startswith("REG") else relationship["from"]
                regulation_counts[regulation_id] += 1
        return {
            "cost_trends": cost_trends,
            "compliance_drift": compliance_drift,
            "supplier_risk_trend": supplier_risk_trend,
            "material_adoption": material_adoption,
            "regulation_exposure": [
                {
                    "regulation": self.regulation_index.get(regulation_id, {}).get("name", regulation_id),
                    "affected_materials": count,
                }
                for regulation_id, count in sorted(regulation_counts.items(), key=lambda item: item[1], reverse=True)[:8]
            ],
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

    # -- Internal helpers ---------------------------------------------------

    def _type_from_node_id(self, node_id: str) -> str:
        prefix_map = {
            "MAT": "material",
            "SUP": "supplier",
            "APP": "application",
            "REG": "regulation",
            "DOC": "document",
            "REP": "report",
            "NEWS": "news",
            "REC": "recycling_stream",
        }
        prefix = str(node_id).split("-")[0]
        return prefix_map.get(prefix, "unknown")

    def materials_at_risk(self) -> list[dict[str, Any]]:
        return build_material_risk_list(self)

    def timeline_for_material(self, material_id: str) -> list[dict[str, Any]]:
        return self.snapshots_by_material.get(material_id, [])

    def backend_status(self) -> list[dict[str, Any]]:
        return build_backend_status(self)

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


# Re-exports so existing imports from this module keep working.
from app.repositories.graph_neo4j import Neo4jAdminRepository as Neo4jAdminRepository  # noqa: E402, F401
from app.repositories.graph_neo4j import Neo4jGraphRepository as Neo4jGraphRepository  # noqa: E402, F401
from app.repositories.graph_neo4j import build_graph_repository as build_graph_repository  # noqa: E402, F401
