from __future__ import annotations

import json
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from app.repositories.graph_repository import Neo4jAdminRepository


QUERIES = {
    "top_food_materials": "MATCH (m:Material) WHERE m.food_contact_safe = true RETURN m.name AS name, m.sustainability_score AS sustainability ORDER BY sustainability DESC LIMIT 5",
    "supplier_risk": "MATCH (s:Supplier)-[:SUPPLIES]->(m:Material) RETURN s.name AS supplier, avg(s.disruption_risk_score) AS risk ORDER BY risk DESC LIMIT 5",
    "document_trace": "MATCH (m:Material)-[:HAS_DOCUMENT]->(d:SourceDocument) RETURN m.material_id AS material_id, count(d) AS docs ORDER BY docs DESC LIMIT 5",
}


def time_query(repo: Neo4jAdminRepository, query: str) -> float:
    started = time.perf_counter()
    repo.run(query)
    return round((time.perf_counter() - started) * 1000, 2)


def benchmark(uri: str, username: str, password: str, label: str) -> dict:
    try:
        repo = Neo4jAdminRepository(uri, username, password)
        timings = {name: time_query(repo, query) for name, query in QUERIES.items()}
        repo.close()
        return {"backend": label, "status": "ok", "timings_ms": timings}
    except Exception as exc:
        return {"backend": label, "status": "skipped", "reason": str(exc)}


def main() -> None:
    settings = get_settings()
    results = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "neo4j": benchmark(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password, "neo4j"),
        "memgraph": benchmark(settings.memgraph_uri, settings.memgraph_username, settings.memgraph_password, "memgraph"),
        "notes": [
            "Use the same generated dataset and ingestion script for both backends.",
            "Memgraph support is benchmark-oriented and optional.",
            "Result consistency should be inspected together with backend-specific planner differences.",
        ],
    }
    output = Path("data/runtime/benchmark_results.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
