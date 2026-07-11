# PackGraph Lab Architecture

PackGraph Lab is a local-first sustainable packaging intelligence demo built around synthetic graph-shaped data. The backend serves the generated dataset immediately through a local repository, while also shipping a repeatable Neo4j ingestion path and optional Memgraph benchmarking path.

## Layers

- `app/services/data_generator.py`: creates the synthetic materials, suppliers, provenance, and temporal snapshots.
- `scripts/ingest_graph.py`: pushes the same dataset into Neo4j with `MERGE`-based repeatable ingestion.
- `app/repositories/graph_repository.py`: provides the local graph-style query layer used by the API and frontend.
- `app/services/query_planner.py`: routes natural-language questions through reviewed intent templates instead of freeform Cypher generation.
- `app/services/scenario_engine.py`: simulates disruptions, cost inflation, compostability prioritization, and future regulation activation.
- `web/`: polished single-page frontend with chat, comparison, provenance, compliance, investigations, and relationship explorer panels.

## Product Flow

1. Generate data into `data/generated`.
2. Start FastAPI and serve the frontend.
3. Optionally ingest the same dataset into Neo4j.
4. Run benchmark comparisons against Neo4j and Memgraph if both are available.

## Safety

- All entities are synthetic and product-branded for PackGraph Lab.
- Natural-language routing is template-based and includes query audit details.
- Investigations are stored locally in `data/runtime/investigations.json`.
