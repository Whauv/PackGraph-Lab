# PackGraph Lab Architecture

PackGraph Lab is now oriented around Neo4j as the primary graph runtime, with synthetic demo data kept available for local product review and `private_data/` used as the preferred path for real or confidential JSON ingestion.

## Core layers

- `app/services/data_generator.py`
  Generates the synthetic demo bundle used when private or live graph data is unavailable.
- `scripts/ingest_graph.py`
  Loads the generated bundle into Neo4j and also ingests flattened private JSON records from `private_data/` as `PrivateRecord` nodes.
- `app/services/private_data_service.py`
  Recursively discovers JSON files under `private_data/`, inspects schema without exposing values, and supports private-record lookup.
- `app/repositories/graph_repository.py`
  Serves the graph-style repository API used by the product shell and Neo4j-backed runtime behavior.
- `app/services/query_planner.py`
  Provides reviewed intent routing and parameter extraction.
- `app/services/query_engine.py`
  Runs the hybrid reasoning pipeline and returns trace metadata, scoring details, and review-gate state.
- `web/`
  Hosts the product shell, guided tour, prompt diary, structured answer panel, and section-level workspaces.

See [repository-map.md](C:\Users\prana\OneDrive\Documents\Playground\packgraph-lab\docs\repository-map.md) for the repo organization guide and [changes/README.md](C:\Users\prana\OneDrive\Documents\Playground\packgraph-lab\docs\changes\README.md) for the lightweight change-log pattern.

## Hybrid reasoning pipeline

Every question follows this read-oriented path:

1. `router`
   Chooses between the graph path and private-data path.
2. `nlp classifier`
   Uses the reviewed planner to classify intent and extract candidate entities.
3. `template retrieval`
   Selects the approved graph/query template rather than freeform Cypher generation.
4. `parameter extraction`
   Combines detected entities, options, location hints, and keyword signals.
5. `cypher execution`
   Executes the repository or Neo4j-backed retrieval path.
6. `graph results`
   Normalizes returned rows for product use.
7. `ensemble scoring / reranking`
   Applies deterministic ranking details before the answer is shown.
8. `optional explanation`
   Builds the answer summary and structured decision panel.
9. `human-review gate`
   Prevents automatic write-back behavior and marks ambiguous private matches for review.

The API response exposes classifier metadata, retrieval details, scoring info, normalized rows, and a stage-by-stage pipeline trace.

## Private data safety

- `private_data/` is ignored by git and can contain nested private subfolders.
- Schema inspection omits values, filenames, and folder names.
- Recursive discovery only returns abstract dataset summaries and field/type coverage.
- Private matches are treated as read-only until a human-review step clears any write-back.

## Review and resolution direction

- Review is the human-in-the-loop checkpoint before new private records become graph write-backs.
- Resolution is the product workflow for cross-graph entity matching, duplicate handling, and merge decisions.
- Schema migration should move through PR-based review and staged approval rather than direct ad hoc graph edits.

## Product flow

1. Generate demo data into `data/generated`.
2. Optionally place confidential JSON under `private_data/`.
3. Start FastAPI and the product shell.
4. Ingest synthetic and private records into Neo4j.
5. Ask questions through the hybrid query pipeline and review trace/debug output in the UI.

## Safety

- Demo entities remain synthetic and product-branded for PackGraph Lab.
- Private schema inspection is metadata-only.
- Investigations are stored locally in `data/runtime/investigations.json`.
- Private record write-back remains gated behind human review.
