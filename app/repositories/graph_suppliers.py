from __future__ import annotations

from copy import deepcopy
from statistics import mean
from typing import Any


def get_supplier(repo, supplier_id: str) -> dict[str, Any] | None:
    supplier = repo.supplier_index.get(supplier_id)
    if not supplier:
        return None
    snapshots = sorted(repo.snapshots_by_supplier.get(supplier_id, []), key=lambda item: item["quarter"])
    materials = [repo.material_index[item] for item in supplier["supplied_material_ids"] if item in repo.material_index]
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


def compare_suppliers(repo, supplier_ids: list[str] | None = None) -> list[dict[str, Any]]:
    suppliers = repo.suppliers if not supplier_ids else [repo.supplier_index[sid] for sid in supplier_ids if sid in repo.supplier_index]
    compared = []
    for supplier in suppliers:
        snapshots = repo.snapshots_by_supplier.get(supplier["supplier_id"], [])
        compared.append(
            {
                **supplier,
                "average_cost_pressure": round(mean(item["price_index"] for item in snapshots), 2) if snapshots else None,
                "average_compliance_rate": round(mean(item["compliance_score"] for item in snapshots), 2) if snapshots else None,
                "latest_snapshot": snapshots[-1] if snapshots else None,
            }
        )
    return sorted(compared, key=lambda item: (-item["esg_score"], item["disruption_risk_score"], item["lead_time_days"]))
