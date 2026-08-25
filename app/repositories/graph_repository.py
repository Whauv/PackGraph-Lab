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
from app.repositories.data_store import get_data_store
from app.repositories.graph_evidence import evidence_for_material as build_evidence_for_material
from app.repositories.graph_evidence import search_documents as run_document_search
from app.repositories.graph_evidence import selected_entity_lookup as resolve_selected_entity_lookup
from app.repositories.graph_evidence import uploaded_record_lookup as resolve_uploaded_record_lookup
from app.repositories.graph_health import backend_status as build_backend_status
from app.repositories.graph_health import graph_health as build_graph_health
from app.repositories.graph_materials import compare_materials as build_material_comparison
from app.repositories.graph_materials import get_material as load_material_detail
from app.repositories.graph_materials import materials_at_risk as build_material_risk_list
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
        self.products = self._build_products()
        self.product_index = {item["product_id"]: item for item in self.products}

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
        return load_material_detail(self, material_id)

    def list_suppliers(self, region: str | None = None) -> list[dict[str, Any]]:
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

    def list_applications(self) -> list[dict[str, Any]]:
        return self.applications

    def list_products(self) -> list[dict[str, Any]]:
        return self.products

    def list_news(self) -> list[dict[str, Any]]:
        return self.material_news

    def explore_autocomplete(self, query: str) -> list[dict[str, Any]]:
        query_lower = query.lower().strip()
        if len(query_lower) < 2:
            return []
        suggestions = []
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

    def _build_products(self) -> list[dict[str, Any]]:
        products = []
        buyer_region_order = ["North America", "Europe", "Asia Pacific", "Latin America", "Middle East", "Africa"]
        buyer_suffixes = ["Procurement Group", "Consumer Brands", "Retail Network", "Manufacturing Cluster"]
        for index, application in enumerate(self.applications, start=1):
            linked_materials = self._materials_for_application(application["application_id"])
            if not linked_materials:
                continue
            linked_suppliers = self._suppliers_for_materials(linked_materials)
            industry_name = self.industry_index.get(application["industry_id"], {}).get("name", "Packaging")
            average_sustainability = round(mean(item["sustainability_score"] for item in linked_materials), 1)
            average_recyclability = round(mean(item["recyclability_score"] for item in linked_materials), 1)
            average_supply_score = round(mean(100 - self.supplier_index[supplier_id]["disruption_risk_score"] for material in linked_materials for supplier_id in material["supplier_ids"] if supplier_id in self.supplier_index), 1)
            buyer_names = [f"{industry_name} {buyer_suffixes[(index + offset) % len(buyer_suffixes)]}" for offset in range(2)]
            buyer_regions = [buyer_region_order[(index + offset) % len(buyer_region_order)] for offset in range(2)]
            products.append(
                {
                    "product_id": f"PROD-{index:03d}",
                    "name": f"{application['name']} product line",
                    "application_id": application["application_id"],
                    "application_name": application["name"],
                    "application_use_case": application["use_case"],
                    "industry_id": application["industry_id"],
                    "industry_name": industry_name,
                    "material_ids": [item["material_id"] for item in linked_materials[:5]],
                    "alternate_material_ids": [item["material_id"] for item in linked_materials[1:4]],
                    "material_categories": list(dict.fromkeys(item["category"] for item in linked_materials)),
                    "supplier_ids": [item["supplier_id"] for item in linked_suppliers[:6]],
                    "supplier_regions": list(dict.fromkeys(region for supplier in linked_suppliers for region in supplier.get("regions_served", []))),
                    "buyer_names": buyer_names,
                    "buyer_regions": buyer_regions,
                    "sustainability_score": average_sustainability,
                    "recyclability_score": average_recyclability,
                    "supply_chain_score": average_supply_score,
                    "match_score": round(mean(item["oxygen_barrier"] + item["seal_strength"] for item in linked_materials) / 2, 1),
                    "compliance_state": "compliant" if all(item["compliance_state"] == "compliant" for item in linked_materials[:3]) else "watch",
                    "thumbnail_tone": self._classify_material(linked_materials[0]),
                }
            )
        return products

    def _thumbnail_label(self, entity_type: str, title: str) -> str:
        prefixes = {
            "material": "MAT",
            "product": "PROD",
            "news": "NEWS",
            "supplier": "SUP",
        }
        return f"{prefixes.get(entity_type, entity_type[:3].upper())} | {title[:18]}"

    def _classify_material(self, material: dict[str, Any]) -> str:
        category = material.get("category", "").lower()
        composition = material.get("composition", "").lower()
        descriptor = material.get("descriptor", "").lower()
        if any(token in category for token in ["ore", "fiber", "pulp"]) or "unrefined" in descriptor:
            return "Natural"
        if any(token in category for token in ["composite", "laminate"]) or "," in composition or "/" in composition:
            return "Compound"
        return "Refined"

    def _explore_material_card(self, material: dict[str, Any], classification: str) -> dict[str, Any]:
        return {
            "entity_type": "material",
            "entity_id": material["material_id"],
            "title": material["name"],
            "subtitle": f"{material['category']} | {material['compliance_state']}",
            "meta": f"Sustainability {material['sustainability_score']} | Recyclability {material['recyclability_score']}",
            "tags": [classification, material["descriptor"], *material["regions_available"][:2]],
            "classification": classification,
            "thumbnail": self._thumbnail_label("material", material["name"]),
            "location_summary": material["regions_available"],
            "focus_material_id": material["material_id"],
            "dashboard_prompt": f"Map the strongest evidence, risks, and substitutes for {material['name']}.",
        }

    def _explore_product_card(self, product: dict[str, Any]) -> dict[str, Any]:
        return {
            "entity_type": "product",
            "entity_id": product["product_id"],
            "title": product["name"],
            "subtitle": f"{product['industry_name']} | {product['application_name']}",
            "meta": f"Match {product['match_score']} | Sustainability {product['sustainability_score']} | Supply {product['supply_chain_score']}",
            "tags": ["Product", *product["material_categories"][:2], *product["buyer_regions"][:1]],
            "classification": "Product",
            "thumbnail": self._thumbnail_label("product", product["name"]),
            "location_summary": list(dict.fromkeys([*product["supplier_regions"][:2], *product["buyer_regions"][:2]])),
            "focus_material_id": product["material_ids"][0] if product["material_ids"] else None,
            "dashboard_prompt": f"Compare alternate materials for product {product['name']} and explain the tradeoffs.",
        }

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
        search_lower = search.lower().strip() if search else ""
        if tab == "products":
            results = []
            for product in self.products:
                if taxonomy and taxonomy.lower() != "product":
                    continue
                if region and region not in product["supplier_regions"] and region not in product["buyer_regions"]:
                    continue
                if category and category.lower() != product["industry_name"].lower() and category.lower() not in [item.lower() for item in product["material_categories"]]:
                    continue
                if supplier_id and supplier_id not in product["supplier_ids"]:
                    continue
                if application_id and application_id != product["application_id"]:
                    continue
                if compliance_state and product["compliance_state"].lower() != compliance_state.lower():
                    continue
                if min_sustainability is not None and product["sustainability_score"] < min_sustainability:
                    continue
                haystack = " ".join([product["name"], product["application_use_case"], product["industry_name"], " ".join(product["buyer_names"])]).lower()
                if search_lower and search_lower not in haystack:
                    continue
                results.append(self._explore_product_card(product))
            return results[:36]

        if tab == "suppliers":
            results = []
            for supplier in self.list_suppliers(region=region):
                supplied_materials = [self.material_index[item] for item in supplier["supplied_material_ids"] if item in self.material_index]
                if taxonomy and taxonomy.lower() not in {"refined", "compound", "natural"}:
                    continue
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
                        "meta": f"Risk {supplier['disruption_risk_score']} | {len(supplied_materials)} materials | {', '.join(supplier['regions_served'][:2])}",
                        "tags": [*supplier["regions_served"][:2], *supplier["certifications"][:2]][:4],
                        "classification": "Supplier",
                        "thumbnail": self._thumbnail_label("supplier", supplier["name"]),
                        "location_summary": supplier["regions_served"][:4],
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
                if region and not any(region == served for served in item.get("regions", item.get("regions_available", []))):
                    linked_suppliers = [self.supplier_index[sid] for sid in item.get("related_supplier_ids", []) if sid in self.supplier_index]
                    if not any(region in supplier.get("regions_served", []) for supplier in linked_suppliers):
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
                        "classification": "Update",
                        "thumbnail": self._thumbnail_label("news", item["title"]),
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
            classification = self._classify_material(material)
            if taxonomy and classification.lower() != taxonomy.lower():
                continue
            if region and region not in material["regions_available"]:
                continue
            if supplier_id and supplier_id not in material["supplier_ids"]:
                continue
            if application_id and application_id not in material["target_applications"]:
                continue
            results.append(self._explore_material_card(material, classification))
        return results[:36]

    def explore_detail(self, entity_type: str, entity_id: str) -> dict[str, Any] | None:
        if entity_type == "material":
            material = self.get_material(entity_id)
            if not material:
                return None
            applications = [self.application_index[item] for item in material["target_applications"] if item in self.application_index]
            buyers = self._buyers_for_material(material)
            suppliers = material["suppliers"]
            return {
                "entity_type": "material",
                "entity_id": material["material_id"],
                "title": material["name"],
                "summary": f"{material['descriptor']} {material['category']} candidate used across {len(applications)} downstream applications with {len(suppliers)} qualified suppliers.",
                "classification": self._classify_material(material),
                "thumbnail": self._thumbnail_label("material", material["name"]),
                "facts": [
                    {"label": "Composition", "value": material["composition"]},
                    {"label": "Compliance", "value": material["compliance_state"]},
                    {"label": "Sustainability", "value": material["sustainability_score"]},
                    {"label": "Food contact", "value": "Approved" if material["food_contact_safe"] else "Review required"},
                ],
                "sections": {
                    "overview": {
                    "summary": material["composition"],
                    "facts": [
                            {"label": "Natural class", "value": self._classify_material(material)},
                            {"label": "Descriptor", "value": material["descriptor"]},
                            {"label": "Regions", "value": ", ".join(material["regions_available"][:4])},
                            {"label": "Compliance", "value": material["compliance_state"].replace("-", " ").title()},
                        ],
                    },
                    "applications": self._application_scores_for_material(material, applications),
                    "suppliers": [
                        {
                            "name": supplier["name"],
                            "location": supplier["country"],
                            "regions": ", ".join(supplier["regions_served"][:3]),
                            "lead_time": f"{supplier['lead_time_days']} days",
                        }
                        for supplier in suppliers[:8]
                    ],
                    "buyers": buyers[:8],
                    "market_signals": self._material_market_signals(material),
                    "sustainability_metrics": [
                        {"label": "Sustainability score", "value": material["sustainability_score"]},
                        {"label": "Recyclability", "value": material["recyclability_score"]},
                        {"label": "Compostability", "value": material["compostability_score"]},
                        {"label": "Cost range", "value": f"{material['cost_range']['low']} to {material['cost_range']['high']} {material['cost_range']['currency']}"},
                    ],
                    "regulatory_requirements": self._regulations_for_material(material["material_id"]),
                },
                "related": {
                    "suppliers": [item["name"] for item in material["suppliers"][:4]],
                    "applications": [item["name"] for item in applications[:4]],
                    "documents": [item["title"] for item in material["documents"][:3]],
                },
                "map_points": self._entity_map_points(material=material, buyers=buyers, suppliers=suppliers),
                "graph": self._material_detail_graph(material, applications, suppliers, buyers),
                "focus_material_id": material["material_id"],
                "dashboard_prompt": f"Trace the graph evidence, supplier risk, and substitute logic for {material['name']}.",
            }

        if entity_type == "product":
            product = self.product_index.get(entity_id)
            if not product:
                return None
            linked_materials = [self.material_index[item] for item in product["material_ids"] if item in self.material_index]
            linked_suppliers = [self.supplier_index[item] for item in product["supplier_ids"] if item in self.supplier_index]
            return {
                "entity_type": "product",
                "entity_id": product["product_id"],
                "title": product["name"],
                "summary": f"{product['industry_name']} product connected to {len(linked_materials)} candidate materials, {len(linked_suppliers)} suppliers, and {len(product['buyer_names'])} buyer references.",
                "classification": "Product",
                "thumbnail": self._thumbnail_label("product", product["name"]),
                "facts": [
                    {"label": "Industry", "value": product["industry_name"]},
                    {"label": "Application", "value": product["application_name"]},
                    {"label": "Compliance", "value": product["compliance_state"]},
                    {"label": "Buyer regions", "value": ", ".join(product["buyer_regions"][:3])},
                ],
                "sections": {
                    "overview": {
                        "summary": product["application_use_case"],
                        "facts": [
                            {"label": "Product type", "value": "Finished market-ready item"},
                            {"label": "Primary demand region", "value": product["buyer_regions"][0]},
                            {"label": "Supplier reach", "value": ", ".join(product["supplier_regions"][:3])},
                            {"label": "Alt materials", "value": len(product["alternate_material_ids"])},
                        ],
                    },
                    "applications": [
                        {
                            "name": product["application_name"],
                            "match_score": product["match_score"],
                            "sustainability_score": product["sustainability_score"],
                            "supply_chain_score": product["supply_chain_score"],
                            "connected_products": [product["name"]],
                        }
                    ],
                    "suppliers": [
                        {
                            "name": supplier["name"],
                            "location": supplier["country"],
                            "regions": ", ".join(supplier["regions_served"][:3]),
                            "lead_time": f"{supplier['lead_time_days']} days",
                        }
                        for supplier in linked_suppliers[:8]
                    ],
                    "buyers": [{"name": item, "region": region_name} for item, region_name in zip(product["buyer_names"], product["buyer_regions"], strict=False)],
                    "market_signals": self._product_market_signals(product),
                    "sustainability_metrics": self._product_sustainability_metrics(product, linked_materials),
                    "regulatory_requirements": self._product_regulatory_requirements(linked_materials),
                    "alternate_materials": [
                        {"name": self.material_index[item]["name"], "reason": "Alternative candidate already linked to this product"}
                        for item in product["alternate_material_ids"] if item in self.material_index
                    ],
                },
                "related": {
                    "materials": [item["name"] for item in linked_materials[:4]],
                    "suppliers": [item["name"] for item in linked_suppliers[:4]],
                    "buyers": product["buyer_names"][:4],
                },
                "map_points": self._entity_map_points(product=product, suppliers=linked_suppliers),
                "graph": self._product_detail_graph(product, linked_materials, linked_suppliers),
                "focus_material_id": linked_materials[0]["material_id"] if linked_materials else None,
                "dashboard_prompt": f"Which material path is strongest for product {product['name']} and what are the supplier or compliance risks?",
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
        if entity_type == "component":
            component = self.get_component(entity_id)
            if not component:
                return None
            return {
                "entity_type": "component",
                "entity_id": component["component_id"],
                "title": component["name"],
                "summary": component.get("summary", "Web-discovered component reference."),
                "facts": component.get("key_facts", []),
                "related": {
                    "materials": [item["name"] for item in component.get("related_materials", [])[:4]],
                    "tags": component.get("tags", [])[:4],
                    "evidence": component.get("evidence", [])[:2],
                },
                "focus_material_id": component.get("related_material_ids", [None])[0],
                "dashboard_prompt": f"What should I know about the component {component['name']} for packaging decisions?",
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

        for product in self.products:
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

        for component in self.runtime_components():
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

    def get_supplier(self, supplier_id: str) -> dict[str, Any] | None:
        return load_supplier_detail(self, supplier_id)

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

    def _buyers_for_material(self, material: dict[str, Any]) -> list[dict[str, Any]]:
        buyers = []
        for offset, application_id in enumerate(material.get("target_applications", [])[:4]):
            application = self.application_index.get(application_id)
            if not application:
                continue
            industry_name = self.industry_index.get(application["industry_id"], {}).get("name", "Packaging")
            buyers.append(
                {
                    "name": f"{industry_name} Demand Group {offset + 1}",
                    "region": material["regions_available"][offset % len(material["regions_available"])],
                    "signal": f"Interested in {application['name'].lower()} supply continuity",
                }
            )
        return buyers

    def _application_scores_for_material(self, material: dict[str, Any], applications: list[dict[str, Any]]) -> list[dict[str, Any]]:
        scored = []
        for application in applications:
            priority = application.get("priority", "barrier")
            match_score = round((material["oxygen_barrier"] + material["seal_strength"] + material["thermal_tolerance"]) / 3, 1)
            if priority == "recyclability":
                match_score = round((match_score + material["recyclability_score"]) / 2, 1)
            sustainability_score = round((material["sustainability_score"] + material["compostability_score"] + material["recyclability_score"]) / 3, 1)
            supply_chain_score = round(mean(100 - self.supplier_index[supplier_id]["disruption_risk_score"] for supplier_id in material["supplier_ids"] if supplier_id in self.supplier_index), 1)
            connected_products = [item["name"] for item in self.products if item["application_id"] == application["application_id"]][:3]
            scored.append(
                {
                    "name": application["name"],
                    "use_case": application["use_case"],
                    "match_score": match_score,
                    "sustainability_score": sustainability_score,
                    "supply_chain_score": supply_chain_score,
                    "connected_products": connected_products,
                }
            )
        return scored

    def _material_market_signals(self, material: dict[str, Any]) -> list[dict[str, Any]]:
        snapshots = self.snapshots_by_material.get(material["material_id"], [])
        current = snapshots[-1] if snapshots else None
        previous = snapshots[-2] if len(snapshots) > 1 else None
        cost_shift = 0 if not current or not previous else round(current["price_index"] - previous["price_index"], 2)
        return [
            {"label": "Current cost index", "value": current["price_index"] if current else "N/A"},
            {"label": "Quarterly cost shift", "value": cost_shift},
            {"label": "Average supplier risk", "value": round(mean(self.supplier_index[supplier_id]["disruption_risk_score"] for supplier_id in material["supplier_ids"] if supplier_id in self.supplier_index), 1)},
        ]

    def _regulations_for_material(self, material_id: str) -> list[dict[str, Any]]:
        rows = []
        for regulation in self.regulations:
            if self._relationship_between(material_id, regulation["regulation_id"]):
                rows.append(
                    {
                        "name": regulation["name"],
                        "region": regulation["region_id"],
                        "effective_on": regulation["effective_on"],
                    }
                )
        return rows[:6]

    def _entity_map_points(
        self,
        material: dict[str, Any] | None = None,
        product: dict[str, Any] | None = None,
        buyers: list[dict[str, Any]] | None = None,
        suppliers: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        points = []
        for supplier in suppliers or []:
            for region in supplier.get("regions_served", [])[:2]:
                points.append({"type": "supplier", "label": supplier["name"], "region": region})
        for buyer in buyers or []:
            points.append({"type": "buyer", "label": buyer["name"], "region": buyer["region"]})
        if material:
            for region in material.get("regions_available", [])[:3]:
                points.append({"type": "material", "label": material["name"], "region": region})
        if product:
            for region in product.get("buyer_regions", [])[:3]:
                points.append({"type": "product", "label": product["name"], "region": region})
        return points

    def _material_detail_graph(
        self,
        material: dict[str, Any],
        applications: list[dict[str, Any]],
        suppliers: list[dict[str, Any]],
        buyers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        nodes = [{"id": material["material_id"], "label": material["name"], "type": "material"}]
        edges = []
        for application in applications[:4]:
            nodes.append({"id": application["application_id"], "label": application["name"], "type": "application"})
            edges.append({"source": material["material_id"], "target": application["application_id"], "label": "Used in"})
        for supplier in suppliers[:4]:
            nodes.append({"id": supplier["supplier_id"], "label": supplier["name"], "type": "supplier"})
            edges.append({"source": supplier["supplier_id"], "target": material["material_id"], "label": "Supplies"})
        for index, buyer in enumerate(buyers[:4], start=1):
            buyer_id = f"buyer-{material['material_id']}-{index}"
            nodes.append({"id": buyer_id, "label": buyer["name"], "type": "buyer"})
            edges.append({"source": material["material_id"], "target": buyer_id, "label": "Bought by"})
        return {"nodes": nodes, "edges": edges}

    def _product_market_signals(self, product: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"label": "Demand region", "value": product["buyer_regions"][0]},
            {"label": "Supply chain score", "value": product["supply_chain_score"]},
            {"label": "Primary industry", "value": product["industry_name"]},
        ]

    def _product_sustainability_metrics(self, product: dict[str, Any], linked_materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"label": "Product sustainability", "value": product["sustainability_score"]},
            {"label": "Product recyclability", "value": product["recyclability_score"]},
            {"label": "Average material compostability", "value": round(mean(item["compostability_score"] for item in linked_materials), 1) if linked_materials else "N/A"},
        ]

    def _product_regulatory_requirements(self, linked_materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
        regulation_ids = []
        for material in linked_materials:
            for regulation in self._regulations_for_material(material["material_id"]):
                regulation_ids.append((regulation["name"], regulation["region"], regulation["effective_on"]))
        unique = list(dict.fromkeys(regulation_ids))
        return [{"name": name, "region": region, "effective_on": effective_on} for name, region, effective_on in unique[:6]]

    def _product_detail_graph(
        self,
        product: dict[str, Any],
        linked_materials: list[dict[str, Any]],
        linked_suppliers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        nodes = [{"id": product["product_id"], "label": product["name"], "type": "product"}]
        edges = []
        for material in linked_materials[:4]:
            nodes.append({"id": material["material_id"], "label": material["name"], "type": "material"})
            edges.append({"source": product["product_id"], "target": material["material_id"], "label": "Uses"})
        for supplier in linked_suppliers[:4]:
            nodes.append({"id": supplier["supplier_id"], "label": supplier["name"], "type": "supplier"})
            edges.append({"source": supplier["supplier_id"], "target": product["product_id"], "label": "Feeds"})
        return {"nodes": nodes, "edges": edges}

    def compare_suppliers(self, supplier_ids: list[str] | None = None) -> list[dict[str, Any]]:
        return build_supplier_comparison(self, supplier_ids)

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
        return build_evidence_for_material(self, material_id)

    def relationship_preview(self, material_id: str | None = None) -> list[dict[str, Any]]:
        return build_relationship_preview(self, material_id)

    def graph_subgraph(self, material_id: str) -> dict[str, Any]:
        return build_graph_subgraph(self, material_id)

    def graph_path(self, source_id: str, target_id: str) -> dict[str, Any]:
        return build_graph_path(self, source_id, target_id)

    def graph_node_insight(self, node_id: str) -> dict[str, Any]:
        insight = build_graph_node_insight(self, node_id)

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
        material_adoption = []
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
                "Coverage can be expanded with pathfinding, filtered aggregations, temporal snapshot joins, and private-data record exploration.",
            ],
            "query_set": query_notes,
        }

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
        self.settings = settings or get_settings()
        self.driver = None
        self.connection_state = "configured"
        self.audit_path = self.settings.packgraph_runtime_dir / "neo4j_query_audit.jsonl"
        if not self.settings.neo4j_test_stub:
            from neo4j import GraphDatabase

            try:
                self.driver = GraphDatabase.driver(
                    self.settings.neo4j_uri,
                    auth=(self.settings.neo4j_user, self.settings.neo4j_password),
                )
                self.driver.verify_connectivity()
                self.connection_state = "connected"
            except Exception as exc:
                self.connection_state = "unavailable"
                raise GraphConnectionError(
                    f"Neo4j is unavailable at {_safe_neo4j_uri(self.settings.neo4j_uri)} for database {self.settings.neo4j_database}."
                ) from exc
        else:
            self.connection_state = "stubbed"
        if self.settings.neo4j_auto_ingest:
            self.sync_bundle_to_neo4j()

    def close(self) -> None:
        if self.driver:
            self.driver.close()

    def sync_bundle_to_neo4j(self) -> None:
        if not self.driver:
            raise GraphConnectionError("Neo4j sync requires a live Neo4j connection.")
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
        if not self.driver:
            raise GraphConnectionError("Uploaded artifact ingest requires a live Neo4j connection.")
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

    def selected_material_lookup(self, material_id: str) -> dict[str, Any] | None:
        if not self.driver:
            return super().selected_material_lookup(material_id)
        query = """
        MATCH (m:Material {material_id: $material_id})
        OPTIONAL MATCH (m)-[:SUPPLIED_BY]->(s:Supplier)
        OPTIONAL MATCH (m)-[:HAS_DOCUMENT]->(d:SourceDocument)
        RETURN properties(m) AS material,
               collect(DISTINCT properties(s)) AS suppliers,
               collect(DISTINCT properties(d)) AS documents
        """
        rows = self._run_graph_query("selected_material_lookup", query, {"material_id": material_id})
        if not rows:
            return None
        row = rows[0]
        material = row.get("material")
        if not material:
            return None
        payload = super().get_material(material_id) or material
        payload["suppliers"] = [item for item in row.get("suppliers", []) if item.get("supplier_id")] or payload.get("suppliers", [])
        payload["documents"] = [item for item in row.get("documents", []) if item.get("document_id")] or payload.get("documents", [])
        return payload

    def selected_supplier_lookup(self, supplier_id: str) -> dict[str, Any] | None:
        if not self.driver:
            return super().selected_supplier_lookup(supplier_id)
        query = """
        MATCH (s:Supplier {supplier_id: $supplier_id})
        OPTIONAL MATCH (s)-[:SUPPLIES]->(m:Material)
        RETURN properties(s) AS supplier,
               collect(DISTINCT properties(m)) AS materials
        """
        rows = self._run_graph_query("selected_supplier_lookup", query, {"supplier_id": supplier_id})
        if not rows:
            return None
        row = rows[0]
        supplier = row.get("supplier")
        if not supplier:
            return None
        payload = super().get_supplier(supplier_id) or supplier
        payload["supplied_materials"] = [item for item in row.get("materials", []) if item.get("material_id")] or payload.get("supplied_materials", [])
        return payload

    def selected_entity_lookup(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        entity_name: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.driver:
            return super().selected_entity_lookup(entity_type, entity_id, entity_name)
        if entity_type == "material" and entity_id:
            material = self.selected_material_lookup(entity_id)
            return {"entity": {"type": "material", "id": entity_id, "label": material.get("name", entity_id)}, "material": material} if material else None
        if entity_type == "supplier" and entity_id:
            supplier = self.selected_supplier_lookup(entity_id)
            return {"entity": {"type": "supplier", "id": entity_id, "label": supplier.get("name", entity_id)}, "supplier": supplier} if supplier else None
        query = """
        MATCH (n)
        WHERE ($entity_id IS NOT NULL AND any(k IN $id_keys WHERE n[k] = $entity_id))
           OR ($entity_name IS NOT NULL AND toLower(coalesce(n.name, n.title, "")) = toLower($entity_name))
        RETURN labels(n)[0] AS label, properties(n) AS props
        LIMIT 1
        """
        rows = self._run_graph_query(
            "selected_entity_lookup",
            query,
            {"entity_id": entity_id, "entity_name": entity_name, "id_keys": self.ID_KEYS},
        )
        if not rows:
            return super().selected_entity_lookup(entity_type, entity_id, entity_name)
        row = rows[0]
        resolved = self._normalize_node(row["label"], row["props"])
        return super().selected_entity_lookup(resolved["type"], resolved["id"], resolved["label"])

    def uploaded_record_lookup(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        entity_name: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.driver:
            return super().uploaded_record_lookup(entity_type, entity_id, entity_name)
        if entity_type in {"component"}:
            return super().uploaded_record_lookup(entity_type, entity_id, entity_name)
        query = """
        MATCH (n)
        WHERE ($entity_id IS NOT NULL AND (n.document_id = $entity_id OR n.report_id = $entity_id))
           OR ($entity_name IS NOT NULL AND toLower(coalesce(n.title, "")) = toLower($entity_name))
        RETURN labels(n)[0] AS label, properties(n) AS props
        LIMIT 1
        """
        rows = self._run_graph_query(
            "uploaded_record_lookup",
            query,
            {"entity_id": entity_id, "entity_name": entity_name},
        )
        if not rows:
            return super().uploaded_record_lookup(entity_type, entity_id, entity_name)
        row = rows[0]
        label = row["label"]
        props = row["props"]
        if label == "SourceDocument":
            return {"record_type": "document", "record": self.document_detail(props.get("document_id", ""))}
        if label == "TestReport":
            return {"record_type": "report", "record": self.document_detail(props.get("report_id", ""))}
        return super().uploaded_record_lookup(entity_type, entity_id, entity_name)

    def backend_status(self) -> list[dict[str, Any]]:
        statuses = super().backend_status()
        statuses[0]["status"] = "ready" if self.connection_state == "connected" else self.connection_state
        return statuses

    def graph_health(self) -> dict[str, Any]:
        return {
            "backend": "neo4j",
            "uri": _safe_neo4j_uri(self.settings.neo4j_uri),
            "database": self.settings.neo4j_database,
            "connected": self.connection_state == "connected",
            "mode": self.connection_state,
        }

    def _run_graph_query(self, query_name: str, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if not self.driver:
            raise GraphConnectionError("Neo4j is not connected. Live graph queries are unavailable.")
        params = parameters or {}
        try:
            with self.driver.session(database=self.settings.neo4j_database) as session:
                explain = session.run(f"EXPLAIN {query}", params)
                explain_summary = explain.consume()
                result = session.run(query, params)
                rows = [dict(record) for record in result]
                result_summary = result.consume()
        except Exception as exc:
            raise GraphQueryFailure(f"Neo4j query '{query_name}' failed against database {self.settings.neo4j_database}.") from exc
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
    return Neo4jGraphRepository(settings)
