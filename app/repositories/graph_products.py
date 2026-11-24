from __future__ import annotations

from statistics import mean
from typing import Any


def classify_material(material: dict[str, Any]) -> str:
    category = material.get("category", "").lower()
    composition = material.get("composition", "").lower()
    descriptor = material.get("descriptor", "").lower()
    if any(token in category for token in ["ore", "fiber", "pulp"]) or "unrefined" in descriptor:
        return "Natural"
    if any(token in category for token in ["composite", "laminate"]) or "," in composition or "/" in composition:
        return "Compound"
    return "Refined"


def thumbnail_label(entity_type: str, title: str) -> str:
    prefixes = {
        "material": "MAT",
        "product": "PROD",
        "news": "NEWS",
        "supplier": "SUP",
    }
    return f"{prefixes.get(entity_type, entity_type[:3].upper())} | {title[:18]}"


def materials_for_application(repo, application_id: str) -> list[dict[str, Any]]:
    return [item for item in repo.materials if application_id in item["target_applications"]]


def suppliers_for_materials(repo, materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    supplier_ids: list[str] = []
    for material in materials:
        supplier_ids.extend(material["supplier_ids"])
    unique = list(dict.fromkeys(supplier_ids))
    return [repo.supplier_index[item] for item in unique if item in repo.supplier_index]


def build_products(repo) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    buyer_region_order = ["North America", "Europe", "Asia Pacific", "Latin America", "Middle East", "Africa"]
    buyer_suffixes = ["Procurement Group", "Consumer Brands", "Retail Network", "Manufacturing Cluster"]
    for index, application in enumerate(repo.applications, start=1):
        linked_materials = materials_for_application(repo, application["application_id"])
        if not linked_materials:
            continue
        linked_suppliers = suppliers_for_materials(repo, linked_materials)
        industry_name = repo.industry_index.get(application["industry_id"], {}).get("name", "Packaging")
        average_sustainability = round(mean(item["sustainability_score"] for item in linked_materials), 1)
        average_recyclability = round(mean(item["recyclability_score"] for item in linked_materials), 1)
        average_supply_score = round(mean(100 - repo.supplier_index[supplier_id]["disruption_risk_score"] for material in linked_materials for supplier_id in material["supplier_ids"] if supplier_id in repo.supplier_index), 1)
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
                "thumbnail_tone": classify_material(linked_materials[0]),
            }
        )
    return products
