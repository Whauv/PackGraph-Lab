from __future__ import annotations

from copy import deepcopy
from statistics import mean
from typing import Any


def get_material(repo, material_id: str) -> dict[str, Any] | None:
    material = repo.material_index.get(material_id)
    if not material:
        return None
    result = deepcopy(material)
    result["suppliers"] = [repo.supplier_index[sid] for sid in material["supplier_ids"] if sid in repo.supplier_index]
    result["snapshots"] = repo.snapshots_by_material.get(material_id, [])
    result["documents"] = [
        doc for doc in repo.all_documents()
        if doc.get("document_id") in material["source_document_ids"] or doc.get("material_id") == material_id
    ]
    result["test_reports"] = [report for report in repo.all_test_reports() if report.get("material_id") == material_id]
    return result


def compare_materials(repo, material_ids: list[str], weights: dict[str, float] | None = None) -> list[dict[str, Any]]:
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
        material = repo.material_index.get(material_id)
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


def materials_at_risk(repo) -> list[dict[str, Any]]:
    risky = []
    for material in repo.materials:
        supplier_scores = [repo.supplier_index[sid]["disruption_risk_score"] for sid in material["supplier_ids"] if sid in repo.supplier_index]
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
