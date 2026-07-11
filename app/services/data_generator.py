from __future__ import annotations

import json
import random
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


SEED = 42
QUARTERS = ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3"]


def clamp(value: float, floor: int = 0, ceiling: int = 100) -> int:
    return max(floor, min(ceiling, round(value)))


def slugify(value: str) -> str:
    return (
        value.lower()
        .replace("&", "and")
        .replace("/", "-")
        .replace(" ", "-")
        .replace(",", "")
        .replace(".", "")
    )


def write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def ensure_generated_data(data_dir: Path) -> None:
    expected = [data_dir / "materials.json", data_dir / "manifest.json"]
    if all(path.exists() for path in expected):
        return
    generate_dataset(data_dir)


def generate_dataset(data_dir: Path) -> dict[str, Any]:
    random.seed(SEED)
    data_dir.mkdir(parents=True, exist_ok=True)

    regions = [
        {"region_id": "REG-NA", "name": "North America"},
        {"region_id": "REG-EU", "name": "Europe"},
        {"region_id": "REG-AP", "name": "Asia Pacific"},
        {"region_id": "REG-LA", "name": "Latin America"},
        {"region_id": "REG-ME", "name": "Middle East"},
    ]
    industries = [
        {"industry_id": "IND-SNACK", "name": "Snack Foods"},
        {"industry_id": "IND-BEV", "name": "Beverages"},
        {"industry_id": "IND-DAIRY", "name": "Dairy"},
        {"industry_id": "IND-HOME", "name": "Home Care"},
        {"industry_id": "IND-PHARMA", "name": "Pharma"},
        {"industry_id": "IND-PET", "name": "Pet Care"},
    ]
    applications = [
        ("APP-001", "Stand-up pouch", "high moisture snacks"),
        ("APP-002", "Flow wrap", "single-serve confectionery"),
        ("APP-003", "Lidding film", "chilled ready meals"),
        ("APP-004", "Retort pouch", "shelf stable sauces"),
        ("APP-005", "Paper mailer", "e-commerce soft goods"),
        ("APP-006", "Produce bag", "fresh produce"),
        ("APP-007", "Blister backing", "pharma dose packs"),
        ("APP-008", "Frozen food overwrap", "frozen meals"),
        ("APP-009", "Coffee pouch", "aroma-sensitive beverages"),
        ("APP-010", "Bakery window bag", "artisanal bread"),
        ("APP-011", "Yogurt lid", "dairy cups"),
        ("APP-012", "Detergent refill pouch", "home care"),
        ("APP-013", "Tea sachet laminate", "dry tea and botanicals"),
        ("APP-014", "Dry pet food bag", "pet nutrition"),
        ("APP-015", "Medical peel pack", "sterile devices"),
        ("APP-016", "Condiment sachet", "food service"),
        ("APP-017", "Fruit punnet wrap", "fresh berries"),
        ("APP-018", "Compostable takeaway bowl", "prepared meals"),
        ("APP-019", "Pharma carton liner", "secondary packaging"),
        ("APP-020", "Protein powder pouch", "sports nutrition"),
    ]
    certifications = [
        ("CERT-001", "FoodSafe EU 41", "food contact"),
        ("CERT-002", "CompostMark EN13432", "compostability"),
        ("CERT-003", "ClosedLoop Ready", "recyclability"),
        ("CERT-004", "ForestFiber Plus", "fiber sourcing"),
        ("CERT-005", "BarrierLab Verified", "barrier performance"),
        ("CERT-006", "LowVOC Seal", "process emissions"),
    ]
    regulations = [
        ("REGU-001", "Food Contact Framework 2030", "food-contact", "2026-10-01"),
        ("REGU-002", "Flexible Film Recyclability Rule", "recyclability", "2026-07-01"),
        ("REGU-003", "PFAS Surface Restriction", "coating", "2026-04-01"),
        ("REGU-004", "Compostability Claim Standard", "compostability", "2026-12-01"),
        ("REGU-005", "Adhesive Residue Limit", "adhesive", "2025-11-01"),
        ("REGU-006", "Virgin Plastic Disclosure", "bioplastic", "2025-09-01"),
        ("REGU-007", "Thermal Seal Migration Rule", "seal", "2026-01-01"),
        ("REGU-008", "Medical Packaging Evidence Act", "pharma", "2026-02-01"),
        ("REGU-009", "Export Fiber Traceability Code", "paper", "2026-06-01"),
        ("REGU-010", "Post-Consumer Content Mandate", "recyclability", "2026-09-15"),
        ("REGU-011", "Moisture Barrier Labeling Rule", "barrier", "2025-12-01"),
        ("REGU-012", "High-Risk Supplier Disclosure", "supplier", "2026-03-01"),
    ]
    recycling_streams = [
        {"stream_id": "REC-001", "name": "Store Drop-off PE", "accepted_categories": ["film", "laminate"]},
        {"stream_id": "REC-002", "name": "Rigid Fiber Recovery", "accepted_categories": ["paper composite"]},
        {"stream_id": "REC-003", "name": "Industrial Compost", "accepted_categories": ["bioplastic", "paper composite"]},
        {"stream_id": "REC-004", "name": "Mixed Flexible Recovery", "accepted_categories": ["film", "coating"]},
        {"stream_id": "REC-005", "name": "Specialty Pharma Waste", "accepted_categories": ["adhesive", "laminate"]},
    ]

    category_templates = [
        ("film", ["PE", "mPE", "EVOH"], ["high clarity", "machine direction seal"], [78, 75, 58, 82, 84]),
        ("bioplastic", ["PLA", "PHA", "starch blend"], ["bio-based", "heat limited"], [62, 66, 41, 68, 79]),
        ("coating", ["waterborne acrylic", "mineral barrier"], ["surface barrier", "print receptive"], [74, 69, 77, 55, 71]),
        ("barrier layer", ["EVOH", "SiOx", "AlOx"], ["aroma retention", "thin gauge"], [91, 85, 72, 48, 62]),
        ("adhesive", ["solvent-free PU", "bio-binder"], ["lamination ready", "bond stability"], [49, 52, 61, 89, 53]),
        ("laminate", ["PE/PE", "PET/PE", "paper/biopolymer"], ["multi-layer", "application tuned"], [83, 79, 76, 80, 67]),
        ("paper composite", ["kraft fiber", "bagasse fiber", "dispersion barrier"], ["renewable fiber", "stiffness"], [67, 73, 88, 63, 81]),
    ]
    countries_by_region = {
        "North America": ["United States", "Canada", "Mexico"],
        "Europe": ["Germany", "Netherlands", "Italy", "Poland", "Spain"],
        "Asia Pacific": ["Japan", "South Korea", "Vietnam", "Thailand", "Australia"],
        "Latin America": ["Brazil", "Chile", "Colombia"],
        "Middle East": ["UAE", "Saudi Arabia", "Turkey"],
    }

    suppliers = []
    supplier_names = [
        "VelaPack Materials", "HarborFlex Systems", "Blue Loop Converting", "Northframe Barrier",
        "GreenSpindle Labs", "OrcaBond Films", "FiberMint Industrial", "Sable Circuit Packaging",
        "Mosaic Seal Works", "AtlasFresh Layers", "CinderBridge Packaging", "TernEco Components",
        "Fieldtrace Polymers", "NovaWrap Source", "BrightShelf Barrier", "HelioPulp Solutions",
        "Cascadia FlexTech", "SoraBond Manufacturing", "ElmRoute Specialty Films", "DeltaNest Materials",
        "LumenWeave Packaging", "Pioneer Crest Supplies", "TerraLatch Goods", "MarlinFiber Group",
        "AsterArc Pack Systems",
    ]
    for index, name in enumerate(supplier_names, start=1):
        region = regions[(index - 1) % len(regions)]["name"]
        country = random.choice(countries_by_region[region])
        esg_score = clamp(58 + index * 1.4 + random.uniform(-8, 8))
        disruption = clamp(68 - index * 0.8 + random.uniform(-12, 12))
        certifications_for_supplier = random.sample([item[1] for item in certifications], k=random.randint(2, 4))
        suppliers.append(
            {
                "supplier_id": f"SUP-{index:03d}",
                "name": name,
                "country": country,
                "regions_served": [region, random.choice(regions)["name"]],
                "lead_time_days": random.randint(14, 60),
                "disruption_risk_score": disruption,
                "esg_score": esg_score,
                "certifications": certifications_for_supplier,
                "supplied_material_ids": [],
            }
        )

    materials = []
    documents = []
    test_reports = []
    relationships = []
    for index in range(75):
        category, composition_parts, descriptors, anchors = category_templates[index % len(category_templates)]
        grade = chr(65 + (index % 5))
        material_id = f"MAT-{index + 1:03d}"
        base_name = f"{category.title().replace(' ', '')} {grade}{index + 11}"
        composition = ", ".join(random.sample(composition_parts, k=min(2, len(composition_parts))))
        category_bias = anchors
        oxygen_barrier = clamp(category_bias[0] + random.uniform(-9, 9))
        moisture_barrier = clamp(category_bias[1] + random.uniform(-9, 9))
        grease_resistance = clamp(category_bias[2] + random.uniform(-10, 10))
        seal_strength = clamp(category_bias[3] + random.uniform(-8, 8))
        flexibility = clamp(category_bias[4] + random.uniform(-8, 8))
        thermal_tolerance = clamp((oxygen_barrier + seal_strength) / 2 + random.uniform(-12, 12))
        transparency = clamp((100 - grease_resistance) * 0.65 + random.uniform(5, 18))
        food_contact_safe = category != "adhesive" or random.random() > 0.35
        recyclability_score = clamp((moisture_barrier + flexibility) / 2 + random.uniform(-15, 8))
        compostability_score = clamp(78 + random.uniform(-10, 12) if category in {"bioplastic", "paper composite"} else 28 + random.uniform(-12, 18))
        sustainability_score = clamp((recyclability_score + compostability_score + random.uniform(30, 75)) / 2)
        cost_low = round(random.uniform(1.8, 5.4), 2)
        cost_high = round(cost_low + random.uniform(0.8, 2.6), 2)
        supplier_count = random.randint(2, 4)
        supplier_pool = random.sample(suppliers, k=supplier_count)
        target_apps = random.sample([app[0] for app in applications], k=random.randint(2, 4))
        region_list = sorted({region for supplier in supplier_pool for region in supplier["regions_served"]})
        compliance_flags = []
        if category == "coating" and random.random() > 0.6:
            compliance_flags.append("pfas-review")
        if not food_contact_safe:
            compliance_flags.append("food-contact-watch")
        if recyclability_score < 55:
            compliance_flags.append("recovery-gap")
        compliance_state = "compliant" if len(compliance_flags) <= 1 else random.choice(["watch", "non-compliant"])
        document_ids = [f"DOC-{index + 1:03d}-A", f"DOC-{index + 1:03d}-B"]
        substitute_ids = []
        materials.append(
            {
                "material_id": material_id,
                "name": base_name,
                "category": category,
                "composition": composition,
                "descriptor": random.choice(descriptors),
                "oxygen_barrier": oxygen_barrier,
                "moisture_barrier": moisture_barrier,
                "grease_resistance": grease_resistance,
                "seal_strength": seal_strength,
                "flexibility": flexibility,
                "thermal_tolerance": thermal_tolerance,
                "transparency": transparency,
                "food_contact_safe": food_contact_safe,
                "recyclability_score": recyclability_score,
                "compostability_score": compostability_score,
                "sustainability_score": sustainability_score,
                "cost_range": {"low": cost_low, "high": cost_high, "currency": "USD/kg"},
                "substitute_material_ids": substitute_ids,
                "target_applications": target_apps,
                "supplier_ids": [supplier["supplier_id"] for supplier in supplier_pool],
                "compliance_flags": compliance_flags,
                "compliance_state": compliance_state,
                "regions_available": region_list,
                "source_document_ids": document_ids,
            }
        )
        for supplier in supplier_pool:
            supplier["supplied_material_ids"].append(material_id)
        doc_types = ["synthetic datasheet", "synthetic declaration", "synthetic chain of custody summary"]
        for doc_index, doc_id in enumerate(document_ids):
            documents.append(
                {
                    "document_id": doc_id,
                    "title": f"{base_name} {doc_types[doc_index]}",
                    "material_id": material_id,
                    "supplier_id": supplier_pool[min(doc_index, len(supplier_pool) - 1)]["supplier_id"],
                    "document_type": doc_types[doc_index],
                    "issued_on": f"2026-{doc_index + 3:02d}-{(index % 20) + 1:02d}",
                    "provenance_score": clamp(76 + random.uniform(-10, 14)),
                    "checksum": slugify(f"{base_name}-{doc_id}-{SEED}"),
                }
            )
        test_reports.append(
            {
                "report_id": f"LAB-{index + 1:03d}",
                "material_id": material_id,
                "title": f"{base_name} barrier and seal validation",
                "lab": random.choice(["Arcwell Test House", "Blue Mesa Labs", "Crescent Validation Works"]),
                "test_date": f"2026-{(index % 6) + 1:02d}-15",
                "oxygen_barrier_result": oxygen_barrier,
                "seal_strength_result": seal_strength,
                "migration_status": "pass" if food_contact_safe else random.choice(["pass", "review"]),
            }
        )

    for index, material in enumerate(materials):
        peers = [item["material_id"] for item in materials if item["category"] == material["category"] and item["material_id"] != material["material_id"]]
        if len(peers) < 3:
            peers = [item["material_id"] for item in materials if item["material_id"] != material["material_id"]]
        material["substitute_material_ids"] = random.sample(peers, k=3)

    application_payload = [
        {
            "application_id": app_id,
            "name": name,
            "use_case": use_case,
            "industry_id": random.choice(industries)["industry_id"],
            "priority": random.choice(["barrier", "cost", "compostability", "recyclability"]),
        }
        for app_id, name, use_case in applications
    ]
    certification_payload = [
        {
            "certification_id": cert_id,
            "name": name,
            "focus": focus,
            "expires_after_months": random.choice([12, 18, 24, 36]),
        }
        for cert_id, name, focus in certifications
    ]
    regulation_payload = [
        {
            "regulation_id": reg_id,
            "name": name,
            "focus": focus,
            "effective_date": effective,
            "active": effective <= "2026-07-11",
        }
        for reg_id, name, focus, effective in regulations
    ]

    snapshots = []
    for material in materials:
        base_cost = material["cost_range"]["low"]
        for supplier_id in material["supplier_ids"]:
            supplier = next(item for item in suppliers if item["supplier_id"] == supplier_id)
            lead_base = supplier["lead_time_days"]
            cert_name = random.choice(supplier["certifications"])
            cert_duration = next(item["expires_after_months"] for item in certification_payload if item["name"] == cert_name)
            for quarter_index, quarter in enumerate(QUARTERS):
                delta = random.uniform(-0.18, 0.24)
                cost = round(base_cost * (1 + delta + quarter_index * 0.03), 2)
                lead = max(7, round(lead_base * (1 + random.uniform(-0.12, 0.28))))
                risk = clamp(supplier["disruption_risk_score"] + quarter_index * random.uniform(-2, 4))
                compliance_score = clamp(material["sustainability_score"] + random.uniform(-18, 10))
                compliance_state = "compliant" if compliance_score >= 63 else random.choice(["watch", "non-compliant"])
                snapshots.append(
                    {
                        "snapshot_id": f"SNP-{material['material_id']}-{supplier_id}-{quarter}",
                        "quarter": quarter,
                        "material_id": material["material_id"],
                        "supplier_id": supplier_id,
                        "price_usd_per_kg": cost,
                        "price_index": round(cost / max(base_cost, 0.1), 2),
                        "lead_time_days": lead,
                        "risk_score": risk,
                        "compliance_score": compliance_score,
                        "compliance_state": compliance_state,
                        "certification_name": cert_name,
                        "certification_expiration": f"2027-{((quarter_index * 2) % 12) + 1:02d}-01",
                        "regulation_watch": random.choice(["Flexible Film Recyclability Rule", "PFAS Surface Restriction", "None"]),
                    }
                )

    for material in materials:
        for app_id in material["target_applications"]:
            relationships.append({"type": "TARGETS_APPLICATION", "from": material["material_id"], "to": app_id})
        for supplier_id in material["supplier_ids"]:
            relationships.append({"type": "SUPPLIED_BY", "from": material["material_id"], "to": supplier_id})
        for doc_id in material["source_document_ids"]:
            relationships.append({"type": "HAS_DOCUMENT", "from": material["material_id"], "to": doc_id})
        for substitute_id in material["substitute_material_ids"]:
            relationships.append({"type": "SUBSTITUTES_WITH", "from": material["material_id"], "to": substitute_id})
        recycling_stream = random.choice(recycling_streams)
        relationships.append({"type": "RECYCLES_INTO", "from": material["material_id"], "to": recycling_stream["stream_id"]})
        for flag in material["compliance_flags"][:2]:
            matched = next((reg["regulation_id"] for reg in regulation_payload if reg["focus"] in flag), regulation_payload[index % len(regulation_payload)]["regulation_id"])
            relationships.append({"type": "REVIEWED_UNDER", "from": material["material_id"], "to": matched})

    for supplier in suppliers:
        for material_id in supplier["supplied_material_ids"]:
            relationships.append({"type": "SUPPLIES", "from": supplier["supplier_id"], "to": material_id})

    investigations_seed = [
        {
            "investigation_id": "INV-001",
            "title": "Snack pouch redesign Q3",
            "focus_material_id": materials[0]["material_id"],
            "notes": "Benchmarking lighter-weight recyclable replacements for a snack pouch line.",
            "shortlisted_material_ids": [materials[0]["material_id"], materials[4]["material_id"], materials[8]["material_id"]],
            "comparison_material_ids": [materials[0]["material_id"], materials[1]["material_id"], materials[2]["material_id"]],
            "decision_rationale": "Prioritize recyclable mono-material options with stable supplier coverage in North America.",
            "status": "open",
        }
    ]

    manifest = {
        "project": "PackGraph Lab",
        "seed": SEED,
        "generated_on": str(date.today()),
        "counts": {
            "materials": len(materials),
            "suppliers": len(suppliers),
            "applications": len(application_payload),
            "regulations": len(regulation_payload),
            "certifications": len(certification_payload),
            "source_documents": len(documents),
            "test_reports": len(test_reports),
            "quarterly_snapshots": len(snapshots),
            "relationships": len(relationships),
        },
        "category_distribution": Counter(item["category"] for item in materials),
    }

    payloads = {
        "materials": materials,
        "suppliers": suppliers,
        "applications": application_payload,
        "regulations": regulation_payload,
        "certifications": certification_payload,
        "recycling_streams": recycling_streams,
        "regions": regions,
        "industries": industries,
        "source_documents": documents,
        "test_reports": test_reports,
        "quarterly_snapshots": snapshots,
        "investigations_seed": investigations_seed,
        "relationships": relationships,
        "manifest": manifest,
    }
    for name, payload in payloads.items():
        write_json(data_dir / f"{name}.json", payload)
    return payloads
