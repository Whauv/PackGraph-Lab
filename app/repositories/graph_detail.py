from __future__ import annotations

from copy import deepcopy
from statistics import mean
from typing import Any

from app.repositories.graph_products import classify_material, thumbnail_label


def _explore_material_card(repo, material: dict[str, Any], classification: str) -> dict[str, Any]:
    return {
        "entity_type": "material",
        "entity_id": material["material_id"],
        "title": material["name"],
        "subtitle": f"{material['category']} | {material['compliance_state']}",
        "meta": f"Sustainability {material['sustainability_score']} | Recyclability {material['recyclability_score']}",
        "tags": [classification, material["descriptor"], *material["regions_available"][:2]],
        "classification": classification,
        "thumbnail": thumbnail_label("material", material["name"]),
        "location_summary": material["regions_available"],
        "focus_material_id": material["material_id"],
        "dashboard_prompt": f"Map the strongest evidence, risks, and substitutes for {material['name']}.",
    }


def _explore_product_card(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_type": "product",
        "entity_id": product["product_id"],
        "title": product["name"],
        "subtitle": f"{product['industry_name']} | {product['application_name']}",
        "meta": f"Match {product['match_score']} | Sustainability {product['sustainability_score']} | Supply {product['supply_chain_score']}",
        "tags": ["Product", *product["material_categories"][:2], *product["buyer_regions"][:1]],
        "classification": "Product",
        "thumbnail": thumbnail_label("product", product["name"]),
        "location_summary": list(dict.fromkeys([*product["supplier_regions"][:2], *product["buyer_regions"][:2]])),
        "focus_material_id": product["material_ids"][0] if product["material_ids"] else None,
        "dashboard_prompt": f"Compare alternate materials for product {product['name']} and explain the tradeoffs.",
    }


def explore_entities(
    repo,
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
        results: list[dict[str, Any]] = []
        for product in repo.products:
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
            results.append(_explore_product_card(product))
        return results[:36]

    if tab == "suppliers":
        results = []
        for supplier in repo.list_suppliers(region=region):
            supplied_materials = [repo.material_index[item] for item in supplier["supplied_material_ids"] if item in repo.material_index]
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
                    "thumbnail": thumbnail_label("supplier", supplier["name"]),
                    "location_summary": supplier["regions_served"][:4],
                    "focus_material_id": supplied_materials[0]["material_id"] if supplied_materials else None,
                    "dashboard_prompt": f"Which risks and substitution options should I inspect for supplier {supplier['name']}?",
                }
            )
        return results[:36]

    if tab == "news":
        results = []
        for item in repo.material_news:
            linked_materials = [repo.material_index[mid] for mid in item["related_material_ids"] if mid in repo.material_index]
            if category and not any(material["category"].lower() == category.lower() for material in linked_materials):
                continue
            if supplier_id and supplier_id not in item["related_supplier_ids"]:
                continue
            if application_id and application_id not in item["related_application_ids"]:
                continue
            if region and not any(region == served for served in item.get("regions", item.get("regions_available", []))):
                linked_suppliers = [repo.supplier_index[sid] for sid in item.get("related_supplier_ids", []) if sid in repo.supplier_index]
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
                    "thumbnail": thumbnail_label("news", item["title"]),
                    "focus_material_id": item["related_material_ids"][0] if item["related_material_ids"] else None,
                    "dashboard_prompt": f"Explain the graph impact of this update: {item['title']}",
                }
            )
        return results[:36]

    results = []
    for material in repo.filter_materials(
        category=category,
        compliance_state=compliance_state,
        min_sustainability=min_sustainability,
        search=search,
    ):
        classification = classify_material(material)
        if taxonomy and classification.lower() != taxonomy.lower():
            continue
        if region and region not in material["regions_available"]:
            continue
        if supplier_id and supplier_id not in material["supplier_ids"]:
            continue
        if application_id and application_id not in material["target_applications"]:
            continue
        results.append(_explore_material_card(repo, material, classification))
    return results[:36]


# ---------------------------------------------------------------------------
# Detail helpers
# ---------------------------------------------------------------------------

def _buyers_for_material(repo, material: dict[str, Any]) -> list[dict[str, Any]]:
    buyers: list[dict[str, Any]] = []
    for offset, application_id in enumerate(material.get("target_applications", [])[:4]):
        application = repo.application_index.get(application_id)
        if not application:
            continue
        industry_name = repo.industry_index.get(application["industry_id"], {}).get("name", "Packaging")
        buyers.append(
            {
                "name": f"{industry_name} Demand Group {offset + 1}",
                "region": material["regions_available"][offset % len(material["regions_available"])],
                "signal": f"Interested in {application['name'].lower()} supply continuity",
            }
        )
    return buyers


def _application_scores_for_material(repo, material: dict[str, Any], applications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for application in applications:
        priority = application.get("priority", "barrier")
        match_score = round((material["oxygen_barrier"] + material["seal_strength"] + material["thermal_tolerance"]) / 3, 1)
        if priority == "recyclability":
            match_score = round((match_score + material["recyclability_score"]) / 2, 1)
        sustainability_score = round((material["sustainability_score"] + material["compostability_score"] + material["recyclability_score"]) / 3, 1)
        supply_chain_score = round(mean(100 - repo.supplier_index[supplier_id]["disruption_risk_score"] for supplier_id in material["supplier_ids"] if supplier_id in repo.supplier_index), 1)
        connected_products = [item["name"] for item in repo.products if item["application_id"] == application["application_id"]][:3]
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


def _material_market_signals(repo, material: dict[str, Any]) -> list[dict[str, Any]]:
    snapshots = repo.snapshots_by_material.get(material["material_id"], [])
    current = snapshots[-1] if snapshots else None
    previous = snapshots[-2] if len(snapshots) > 1 else None
    cost_shift = 0 if not current or not previous else round(current["price_index"] - previous["price_index"], 2)
    return [
        {"label": "Current cost index", "value": current["price_index"] if current else "N/A"},
        {"label": "Quarterly cost shift", "value": cost_shift},
        {"label": "Average supplier risk", "value": round(mean(repo.supplier_index[supplier_id]["disruption_risk_score"] for supplier_id in material["supplier_ids"] if supplier_id in repo.supplier_index), 1)},
    ]


def _regulations_for_material(repo, material_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for regulation in repo.regulations:
        if repo._relationship_between(material_id, regulation["regulation_id"]):
            rows.append(
                {
                    "name": regulation["name"],
                    "region": regulation["region_id"],
                    "effective_on": regulation["effective_on"],
                }
            )
    return rows[:6]


def _entity_map_points(
    material: dict[str, Any] | None = None,
    product: dict[str, Any] | None = None,
    buyers: list[dict[str, Any]] | None = None,
    suppliers: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
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
    material: dict[str, Any],
    applications: list[dict[str, Any]],
    suppliers: list[dict[str, Any]],
    buyers: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [{"id": material["material_id"], "label": material["name"], "type": "material"}]
    edges: list[dict[str, Any]] = []
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


def _product_market_signals(product: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"label": "Demand region", "value": product["buyer_regions"][0]},
        {"label": "Supply chain score", "value": product["supply_chain_score"]},
        {"label": "Primary industry", "value": product["industry_name"]},
    ]


def _product_sustainability_metrics(product: dict[str, Any], linked_materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"label": "Product sustainability", "value": product["sustainability_score"]},
        {"label": "Product recyclability", "value": product["recyclability_score"]},
        {"label": "Average material compostability", "value": round(mean(item["compostability_score"] for item in linked_materials), 1) if linked_materials else "N/A"},
    ]


def _product_regulatory_requirements(repo, linked_materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    regulation_ids: list[tuple[str, str, str]] = []
    for material in linked_materials:
        for regulation in _regulations_for_material(repo, material["material_id"]):
            regulation_ids.append((regulation["name"], regulation["region"], regulation["effective_on"]))
    unique = list(dict.fromkeys(regulation_ids))
    return [{"name": name, "region": region, "effective_on": effective_on} for name, region, effective_on in unique[:6]]


def _product_detail_graph(
    product: dict[str, Any],
    linked_materials: list[dict[str, Any]],
    linked_suppliers: list[dict[str, Any]],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [{"id": product["product_id"], "label": product["name"], "type": "product"}]
    edges: list[dict[str, Any]] = []
    for material in linked_materials[:4]:
        nodes.append({"id": material["material_id"], "label": material["name"], "type": "material"})
        edges.append({"source": product["product_id"], "target": material["material_id"], "label": "Uses"})
    for supplier in linked_suppliers[:4]:
        nodes.append({"id": supplier["supplier_id"], "label": supplier["name"], "type": "supplier"})
        edges.append({"source": supplier["supplier_id"], "target": product["product_id"], "label": "Feeds"})
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# explore_detail
# ---------------------------------------------------------------------------

def explore_detail(repo, entity_type: str, entity_id: str) -> dict[str, Any] | None:
    if entity_type == "material":
        material = repo.get_material(entity_id)
        if not material:
            return None
        applications = [repo.application_index[item] for item in material["target_applications"] if item in repo.application_index]
        buyers = _buyers_for_material(repo, material)
        suppliers = material["suppliers"]
        return {
            "entity_type": "material",
            "entity_id": material["material_id"],
            "title": material["name"],
            "summary": f"{material['descriptor']} {material['category']} candidate used across {len(applications)} downstream applications with {len(suppliers)} qualified suppliers.",
            "classification": classify_material(material),
            "thumbnail": thumbnail_label("material", material["name"]),
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
                        {"label": "Natural class", "value": classify_material(material)},
                        {"label": "Descriptor", "value": material["descriptor"]},
                        {"label": "Regions", "value": ", ".join(material["regions_available"][:4])},
                        {"label": "Compliance", "value": material["compliance_state"].replace("-", " ").title()},
                    ],
                },
                "applications": _application_scores_for_material(repo, material, applications),
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
                "market_signals": _material_market_signals(repo, material),
                "sustainability_metrics": [
                    {"label": "Sustainability score", "value": material["sustainability_score"]},
                    {"label": "Recyclability", "value": material["recyclability_score"]},
                    {"label": "Compostability", "value": material["compostability_score"]},
                    {"label": "Cost range", "value": f"{material['cost_range']['low']} to {material['cost_range']['high']} {material['cost_range']['currency']}"},
                ],
                "regulatory_requirements": _regulations_for_material(repo, material["material_id"]),
            },
            "related": {
                "suppliers": [item["name"] for item in material["suppliers"][:4]],
                "applications": [item["name"] for item in applications[:4]],
                "documents": [item["title"] for item in material["documents"][:3]],
            },
            "map_points": _entity_map_points(material=material, buyers=buyers, suppliers=suppliers),
            "graph": _material_detail_graph(material, applications, suppliers, buyers),
            "focus_material_id": material["material_id"],
            "dashboard_prompt": f"Trace the graph evidence, supplier risk, and substitute logic for {material['name']}.",
        }

    if entity_type == "product":
        product = repo.product_index.get(entity_id)
        if not product:
            return None
        linked_materials = [repo.material_index[item] for item in product["material_ids"] if item in repo.material_index]
        linked_suppliers = [repo.supplier_index[item] for item in product["supplier_ids"] if item in repo.supplier_index]
        return {
            "entity_type": "product",
            "entity_id": product["product_id"],
            "title": product["name"],
            "summary": f"{product['industry_name']} product connected to {len(linked_materials)} candidate materials, {len(linked_suppliers)} suppliers, and {len(product['buyer_names'])} buyer references.",
            "classification": "Product",
            "thumbnail": thumbnail_label("product", product["name"]),
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
                "market_signals": _product_market_signals(product),
                "sustainability_metrics": _product_sustainability_metrics(product, linked_materials),
                "regulatory_requirements": _product_regulatory_requirements(repo, linked_materials),
                "alternate_materials": [
                    {"name": repo.material_index[item]["name"], "reason": "Alternative candidate already linked to this product"}
                    for item in product["alternate_material_ids"] if item in repo.material_index
                ],
            },
            "related": {
                "materials": [item["name"] for item in linked_materials[:4]],
                "suppliers": [item["name"] for item in linked_suppliers[:4]],
                "buyers": product["buyer_names"][:4],
            },
            "map_points": _entity_map_points(product=product, suppliers=linked_suppliers),
            "graph": _product_detail_graph(product, linked_materials, linked_suppliers),
            "focus_material_id": linked_materials[0]["material_id"] if linked_materials else None,
            "dashboard_prompt": f"Which material path is strongest for product {product['name']} and what are the supplier or compliance risks?",
        }

    if entity_type == "supplier":
        supplier = repo.get_supplier(entity_id)
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
        item = repo.news_index.get(entity_id)
        if not item:
            return None
        related_materials = [repo.material_index[mid]["name"] for mid in item["related_material_ids"] if mid in repo.material_index]
        related_suppliers = [repo.supplier_index[sid]["name"] for sid in item["related_supplier_ids"] if sid in repo.supplier_index]
        related_applications = [repo.application_index[aid]["name"] for aid in item["related_application_ids"] if aid in repo.application_index]
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
        component = repo.get_component(entity_id)
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
