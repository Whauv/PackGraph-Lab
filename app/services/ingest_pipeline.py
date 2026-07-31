from __future__ import annotations

from collections import Counter
from typing import Any

from app.repositories.graph_repository import Neo4jAdminRepository


ENTITY_MAP = {
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


RELATION_QUERIES = {
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


class IngestPipeline:
    def __init__(self, repo: Neo4jAdminRepository):
        self.repo = repo

    def ingest_generated_bundle(self, store: dict[str, Any], normalize) -> dict[str, Any]:
        node_metrics = {}
        edge_metrics = {}
        for key, (label, id_key) in ENTITY_MAP.items():
            query = f"""
            UNWIND $rows AS row
            MERGE (n:{label} {{{id_key}: row.{id_key}}})
            SET n += row
            """
            rows = [normalize(row) for row in store[key]]
            self.repo.run(query, {"rows": rows})
            node_metrics[key] = {"label": label, "created_or_merged_nodes": len(rows)}

        for rel_type, query in RELATION_QUERIES.items():
            rows = [rel for rel in store["relationships"] if rel["type"] == rel_type]
            self.repo.run(query, {"rows": rows})
            edge_metrics[rel_type] = {"created_or_merged_edges": len(rows)}
        return {"nodes": node_metrics, "edges": edge_metrics}

    def ingest_external_records(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {"nodes": {}, "edges": {}}
        self.repo.run(
            """
            UNWIND $rows AS row
            MERGE (n:PrivateRecord {private_record_id: row.private_record_id})
            SET n += row
            """,
            {"rows": rows},
        )
        domain_counts = Counter(row.get("entity_hint", "record") for row in rows)
        return {
            "nodes": {
                domain: {"label": "PrivateRecord", "created_or_merged_nodes": count}
                for domain, count in sorted(domain_counts.items())
            },
            "edges": {},
        }
