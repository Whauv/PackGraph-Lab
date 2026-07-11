from __future__ import annotations

import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.repositories.data_store import get_data_store
from app.repositories.graph_repository import Neo4jAdminRepository


CONSTRAINTS = [
    "CREATE CONSTRAINT material_id IF NOT EXISTS FOR (m:Material) REQUIRE m.material_id IS UNIQUE",
    "CREATE CONSTRAINT supplier_id IF NOT EXISTS FOR (s:Supplier) REQUIRE s.supplier_id IS UNIQUE",
    "CREATE CONSTRAINT application_id IF NOT EXISTS FOR (a:Application) REQUIRE a.application_id IS UNIQUE",
    "CREATE CONSTRAINT regulation_id IF NOT EXISTS FOR (r:Regulation) REQUIRE r.regulation_id IS UNIQUE",
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:SourceDocument) REQUIRE d.document_id IS UNIQUE",
]


def main() -> None:
    settings = get_settings()
    store = get_data_store().load_bundle()
    repo = Neo4jAdminRepository(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)
    started = time.perf_counter()
    try:
        for query in CONSTRAINTS:
            repo.run(query)

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
        for key, (label, id_key) in entity_map.items():
            query = f"""
            UNWIND $rows AS row
            MERGE (n:{label} {{{id_key}: row.{id_key}}})
            SET n += row
            """
            repo.run(query, {"rows": store[key]})

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
        for rel_type, query in relation_queries.items():
            rows = [rel for rel in store["relationships"] if rel["type"] == rel_type]
            repo.run(query, {"rows": rows})

        elapsed = round(time.perf_counter() - started, 3)
        print({"status": "ok", "elapsed_seconds": elapsed, "counts": store["manifest"]["counts"]})
    finally:
        repo.close()


if __name__ == "__main__":
    main()
