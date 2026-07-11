from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from statistics import mean
from typing import Any

from app.core.config import get_settings
from app.repositories.data_store import get_data_store


class LocalGraphRepository:
    def __init__(self) -> None:
        bundle = get_data_store().load_bundle()
        self.bundle = bundle
        self.materials = bundle["materials"]
        self.suppliers = bundle["suppliers"]
        self.applications = bundle["applications"]
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
        self.snapshots_by_supplier = defaultdict(list)
        self.snapshots_by_material = defaultdict(list)
        for snapshot in self.snapshots:
            self.snapshots_by_supplier[snapshot["supplier_id"]].append(snapshot)
            self.snapshots_by_material[snapshot["material_id"]].append(snapshot)

    def list_materials(self) -> list[dict[str, Any]]:
        return self.materials

    def get_material(self, material_id: str) -> dict[str, Any] | None:
        material = self.material_index.get(material_id)
        if not material:
            return None
        result = deepcopy(material)
        result["suppliers"] = [self.supplier_index[sid] for sid in material["supplier_ids"] if sid in self.supplier_index]
        result["snapshots"] = self.snapshots_by_material.get(material_id, [])
        result["documents"] = [doc for doc in self.documents if doc["document_id"] in material["source_document_ids"]]
        result["test_reports"] = [report for report in self.test_reports if report["material_id"] == material_id]
        return result

    def list_suppliers(self) -> list[dict[str, Any]]:
        return self.suppliers

    def list_applications(self) -> list[dict[str, Any]]:
        return self.applications

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
        docs = [doc for doc in self.documents if doc["document_id"] in material["source_document_ids"]]
        reports = [report for report in self.test_reports if report["material_id"] == material_id]
        return {"material": material, "documents": docs, "test_reports": reports}

    def relationship_preview(self, material_id: str | None = None) -> list[dict[str, Any]]:
        links = self.relationships
        if material_id:
            links = [rel for rel in links if rel["from"] == material_id or rel["to"] == material_id]
        return links[:80]

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
