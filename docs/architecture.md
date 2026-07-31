# PackGraph Lab Architecture

PackGraph Lab is now oriented around Neo4j as the primary graph runtime, with synthetic demo data kept available for local product review and `private_data/` used as the preferred path for real or confidential JSON ingestion.

## Core layers

- `app/services/data_generator.py`
  Generates the synthetic demo bundle used when private or live graph data is unavailable.
- `scripts/ingest_graph.py`
  Loads the generated bundle into Neo4j and now profiles/ingests recursive JSON folders plus optional SQLite sources with provenance metadata and duplicate reporting.
- `app/services/private_data_service.py`
  Recursively discovers JSON files under `private_data/`, can inspect optional SQLite sources, hides sensitive values, reports duplicates, and produces provenance-ready ingest rows.
- `app/services/ingest_sources.py`
  Resolves CLI-vs-env ingest source selection so local source overrides do not require code changes.
- `app/services/ingest_pipeline.py`
  Splits generated-bundle ingest and external-record ingest into smaller modules with per-domain node/edge metrics.
- `app/repositories/graph_repository.py`
  Serves the graph-style repository API used by the product shell and Neo4j-backed runtime behavior.
- `app/services/query_planner.py`
  Provides reviewed intent routing and parameter extraction.
- `app/services/query_engine.py`
  Runs the hybrid reasoning pipeline and returns trace metadata, scoring details, review-gate state, explicit agent tool traces, evidence profiling, project memory, and review staging metadata.
- `app/services/agent_tools.py`
  Defines the explicit toolbelt used by the controlled graph assistant.
- `app/services/agent_state_machine.py`
  Defines the strict chat query state progression.
- `app/services/agent_memory.py`
  Stores lightweight local project/session memory in staging JSON.
- `app/services/agent_review.py`
  Stages human-review candidates before any write-back behavior.
- `app/services/entity_resolution_agent.py`
  Detects alias and duplicate risk in returned rows.
- `agents/packgraph_lab_agent/agent.py`
  Provides the optional Google ADK-compatible wrapper without changing the default local runtime.
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

## Controlled agent layer

The chat path is now structured as a controlled agent surface rather than a plain query endpoint. Each request emits:

- `agent_state_machine`
- `agent_tools`
- `agent_orchestration`
- `investigation_plan`
- `evidence_profile`
- `missing_evidence`
- `project_memory`
- `review_candidate`
- `entity_resolution`

The state machine is:

1. `question_received`
2. `intent_classified`
3. `entities_resolved`
4. `tools_selected`
5. `graph_queried`
6. `evidence_retrieved`
7. `results_scored`
8. `answer_generated`
9. `review_checked`

This keeps the runtime deterministic, inspectable, and safer to extend without unconstrained graph writes.

## Private data safety

- `private_data/` is ignored by git and can contain nested private subfolders.
- Schema inspection omits values, filenames, and folder names.
- Recursive discovery only returns abstract dataset summaries and field/type coverage.
- Private matches are treated as read-only until a human-review step clears any write-back.

## Ingest observability

- Source profiling runs before ingest and can be used with `--profile-only`.
- Duplicate-content groups are reported before graph writes.
- External rows include `provenance_id`, `source_record_id`, `parser_name`, and `parser_version`.
- Per-domain ingest metrics are emitted for generated nodes/edges and external record loads.

## Review and resolution direction

- Review is the human-in-the-loop checkpoint before new private records become graph write-backs.
- Resolution is the product workflow for cross-graph entity matching, duplicate handling, and merge decisions.
- Schema migration should move through PR-based review and staged approval rather than direct ad hoc graph edits.
- Review candidates are staged in `data/staging/agent_review_candidates.json`.
- Lightweight project memory is stored in `data/staging/project_memory.json`.
- Agent audits are written to `data/runtime/agent_audit.jsonl`.
- Review exports/imports are handled through `scripts/review_workflow.py`.
- Entity-resolution audit and cached match decisions are stored under `data/runtime/`.

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
