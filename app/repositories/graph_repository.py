from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
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

    def list_materials(self) -> list[dict[str, Any]]:
        return self.materials

    def filter_materials(
        self,
        region: str | None = None,
        category: str | None = None,
        compliance_state: str | None = None,
        min_sustainability: int | None = None,
        search: str | None = None,
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
        return materials

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
        documents = self.documents
        reports = self.test_reports
        if material_id:
            documents = [item for item in documents if item["material_id"] == material_id]
            reports = [item for item in reports if item["material_id"] == material_id]
        results = []
        for document in documents:
            haystack = " ".join([document["title"], document["document_type"], document["supplier_id"]]).lower()
            if query_lower in haystack:
                results.append({"type": "document", **document})
        for report in reports:
            haystack = " ".join([report["title"], report["lab"], report["migration_status"]]).lower()
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
        return alerts[:14]

    def analytics_overview(self) -> dict[str, Any]:
        snapshots_by_quarter = defaultdict(list)
        for snapshot in self.snapshots:
            snapshots_by_quarter[snapshot["quarter"]].append(snapshot)
        cost_trends = []
        compliance_drift = []
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
        supplier_performance = self.compare_suppliers()[:8]
        return {
            "cost_trends": cost_trends,
            "compliance_drift": compliance_drift,
            "supplier_performance": supplier_performance,
        }

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
