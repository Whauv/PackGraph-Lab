# PackGraph Lab

PackGraph Lab is a local-first product prototype for synthetic packaging intelligence. It is designed to show how a graph-native system can support material selection, supplier evaluation, compliance review, document evidence tracing, and scenario planning for packaging teams.

The project uses synthetic data for demo mode, supports private JSON ingestion from `private_data/`, uses Neo4j as the primary graph backend, and exposes a multi-surface frontend that behaves like a real product rather than a single demo screen.

## What the project is

PackGraph Lab models a packaging decision environment where materials, suppliers, applications, regulations, documents, certifications, recycling streams, regions, and quarterly operating snapshots are linked together.

Instead of treating each dataset as an isolated table, the product treats the decision as a connected graph. That makes it easier to answer questions like:

- Which food-safe materials are still viable if supplier risk increases?
- Which substitute materials preserve recyclability or compliance claims?
- Which documents support a material decision, and what evidence is still missing?
- What changes if a regulation activates next quarter?
- Which suppliers, certifications, and regional constraints affect a shortlist?

## Why this project exists

Packaging decisions are not single-variable decisions. A material can look strong on performance but fail on supplier concentration, certification coverage, regulatory timing, or evidence completeness. PackGraph Lab exists to demonstrate a more product-like way to navigate those tradeoffs:

- start with search and decision guidance
- move into comparison and evidence review
- inspect the graph around a candidate
- contribute new knowledge and discuss findings in context

## Product surfaces

The product is organized into four working modes.

### 1. Dashboard

The core decision workspace.

It currently includes:

- Overview surface for search, filtering, and structured answers
- Workbench surface for comparison, evidence review, exports, saved investigations, and scenarios
- Intelligence surface for graph inspection, node context, watchlists, trends, and timeline review

### 2. Explore

A browse-first research surface for opening materials, applications, suppliers, and related updates before asking graph questions.

It includes:

- tabbed entity browsing
- search and filtering
- selected-entity detail view
- saved searches
- jump-to-dashboard workflow

### 3. Contribute

A role-based contribution flow for submitting structured knowledge into the system.

It includes:

- contributor role cards
- role detail and permissions
- structured submission form
- review queue
- contribution status and recent activity

### 4. Community

A discussion layer for graph-aware conversation around materials, suppliers, regulations, sustainability, and sourcing signals.

It includes:

- channel browsing
- thread feed
- linked-material discussion context
- post creation
- thread detail and replies

## What is implemented right now

### Data and graph model

- Synthetic data generation for materials, suppliers, applications, regulations, certifications, documents, test reports, recycling streams, industries, regions, and quarterly snapshots
- Graph-oriented domain model with linked entities and 1,000+ generated relationships
- Local generated bundle used for immediate demo runtime
- Neo4j Community Edition ingestion path with repeatable `MERGE`-based loading
- Recursive private JSON discovery from `private_data/` with schema-safe inspection and ingestable flattened records

### Backend

- FastAPI backend with endpoints for materials, suppliers, applications, investigations, recommendations, natural-language queries, scenarios, backend status, compliance, relationships, contributions, community, search, and supporting drilldowns
- Safe query-planning layer that uses reviewed intent routing instead of unconstrained Cypher generation
- Hybrid reasoning pipeline with router, classifier metadata, reviewed template retrieval, parameter extraction, scoring details, pipeline trace, and human-review gate metadata
- Controlled agentic orchestration with explicit tools, strict state-machine output, evidence profiling, local project memory, review-candidate staging, and entity-resolution checks
- Runtime SQLite control plane with schema migrations for auth, sessions, workspaces, saved searches, jobs, idempotency records, review candidates, and review history
- Real login/session handling with org-aware users, hashed passwords, scoped role permissions, and audit-ready review actions
- Durable background job flow for ingest, ER evaluation, review imports, and other heavy operations with retries, status tracking, and dead-letter behavior
- API hardening through stronger request validation, rate limiting, idempotent mutation endpoints, structured error envelopes, and readiness/live health endpoints
- Observability support for JSONL event logs, request metrics snapshots, runtime health checks, and job backlog summaries
- Flexible local-source ingest support for recursive JSON folders and optional SQLite sources selected from CLI or `.env`
- Ingest profiling with schema/source summaries, duplicate-content reporting, nested-folder depth summaries, structured validation errors, provenance metadata, resumable run-state files, and per-domain metrics
- Review workflow support for summaries, enriched pending export payloads, reviewed-decision import, and structured audit logging
- Local-first ER controls with hashed decision cache keys, configurable confidence thresholds, persistent audit trails, and evaluation dataset support
- Operator status/dashboard and graph-schema metadata scaffolding for safer local administration
- Scenario engine for supplier outages, regulation activation, reformulation targets, and cost constraints
- Document intelligence support for uploaded evidence metadata and extracted field presentation
- Export support for PDF and CSV flows
- Workspace and investigation persistence using local runtime state

### Frontend

- Landing page with product overview, setup guidance, workflow framing, and entry links
- Dashboard with structured answer panel, prompt diary, result/debug split, evidence workspace, graph explorer, supplier and regulation drilldowns, trend panels, and timeline panels
- Light and dark theme support
- Explore, Contribute, and Community product sections
- Guided tour system across Chat, Explore, Projects, Contribute, Community, Review, and Resolution flows
- Graph controls including presets, branch filters, zoom controls, path tracing, and interaction-focused graph context

## Core capabilities

- Search across materials, suppliers, regulations, documents, and reports
- Ask natural-language product questions through a reviewed planner
- Compare multiple materials with weighted ranking
- Inspect compliance pressure and supplier exposure
- Trace document evidence and extracted fields
- Save investigations and workspace context
- Run what-if scenarios and review scenario history
- Open node relationships and shortest paths in the graph explorer
- Review supplier and regulation detail panels
- Browse entity records before entering decision mode
- Submit structured contributions and review queues
- Discuss materials and sourcing topics in community threads

## Example product workflow

1. Open the landing page and jump into the product workspace.
2. Use Overview to search for a material family, supplier, or regulation.
3. Ask a focused question in the structured answer panel.
4. Move to Workbench if the answer produces a real shortlist.
5. Compare candidates, review evidence, and save the decision rationale.
6. Open Intelligence to inspect graph context around the selected material.
7. Run a scenario if the decision is sensitive to supplier outage, regulation timing, or cost.
8. Use Explore, Contribute, or Community as supporting product surfaces around the same graph context.

## Architecture summary

At a high level, the project works like this:

```mermaid
flowchart LR
    A["Synthetic data generator"] --> B["Generated JSON bundle"]
    P["private_data JSON"] --> Q["Schema-safe private inspector"]
    B --> C["Local graph repository"]
    B --> D["Neo4j ingestion script"]
    P --> D
    D --> E["Neo4j Community Edition"]
    C --> F["Hybrid query router"]
    Q --> F
    F --> G["NLP classifier + reviewed template retrieval"]
    G --> H["Parameter extraction + Cypher execution"]
    H --> I["Graph/private results"]
    I --> J["Ensemble scoring + reranking"]
    J --> K["Structured answer panel + debug trace"]
    K --> L["Human review gate"]
    C --> M["Scenario engine"]
    C --> N["Document intelligence and evidence services"]
    C --> O["Investigations, workspaces, contributions, and community services"]
    L --> R["Dashboard / Explore / Contribute / Community"]
    M --> R
    N --> R
    O --> R
    E --> H
```

For more detail, see:

- [Architecture notes](C:\Users\prana\OneDrive\Documents\Playground\packgraph-lab\docs\architecture.md)
- [Repository map](C:\Users\prana\OneDrive\Documents\Playground\packgraph-lab\docs\repository-map.md)
- [Change tracking guide](C:\Users\prana\OneDrive\Documents\Playground\packgraph-lab\docs\changes\README.md)

## Repository structure

- `app/`
  FastAPI app, models, repositories, and services.
- `data/`
  Synthetic generated seed data plus local runtime files.
- `private_data/`
  Ignored local-only JSON for confidential or real ingestion experiments.
- `docs/`
  Architecture, repository guidance, and change-tracking notes.
- `queries/`
  Example Cypher query files.
- `scripts/`
  Data generation, ingestion, and benchmark scripts.
- `tests/`
  Automated backend-focused tests.
- `web/`
  Landing page, product HTML, frontend assets, and page modules.

## Local run

### Option 1: direct Python run

Use this when you want the fastest local developer workflow.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python scripts/generate_data.py
python scripts/migrate_runtime.py
python scripts/ingest_graph.py
python -m uvicorn app.main:app --reload
```

Open:

- landing page: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- product workspace: [http://127.0.0.1:8000/product](http://127.0.0.1:8000/product)

Notes:

- This path assumes Neo4j Community Edition is available at `bolt://localhost:7687` if you want live graph execution.
- If Neo4j is unavailable, the app can still fall back to the local JSON-backed repository for UI review and non-live demo flows.

## Ingest and verification commands

### Initialize runtime state

Create or upgrade the runtime control-plane database before starting operational flows:

```bash
python scripts/migrate_runtime.py
```

### Profile local sources before ingest

This scans JSON subfolders recursively and optionally profiles a SQLite source if configured.

```bash
python scripts/ingest_graph.py --profile-only
```

Override the ingest sources from the CLI:

```bash
python scripts/ingest_graph.py --profile-only --json-source-dir .\\private_data --sqlite-path .\\local_records.sqlite
```

### Run ingest

```bash
python scripts/ingest_graph.py
```

Dry-run the ingest without writing to Neo4j:

```bash
python scripts/ingest_graph.py --dry-run
```

Limit a large nested folder scan:

```bash
python scripts/ingest_graph.py --profile-only --max-files 25
```

Resume a previous run-state artifact:

```bash
python scripts/ingest_graph.py --resume-run-id ING-20260802091500-ABC123
```

Profile and save the observability report:

```bash
python scripts/ingest_graph.py --report-path .\\smoke-test-output\\ingest-report.json
```

Skip generated demo bundle ingest and load only local JSON / SQLite records:

```bash
python scripts/ingest_graph.py --skip-generated
```

### Review export / import

Review pending items:

```bash
python scripts/review_workflow.py summary
```

Export pending review items:

```bash
python scripts/review_workflow.py export --output .\\review-exports\\pending-review.json
```

Import reviewed decisions and optionally apply them to the persistent match cache:

```bash
python scripts/review_workflow.py import --input .\\review-exports\\reviewed-decisions.json --apply
```

### ER evaluation

```bash
python scripts/evaluate_entity_resolution.py
```

### Operator status

```bash
python scripts/status_dashboard.py
```

### Graph schema metadata

```bash
python scripts/migrate_graph_schema.py --apply --notes "{\"source\":\"local migration\"}"
```

### Background jobs

Queue long-running operational work:

```bash
python scripts/run_jobs.py --limit 10
```

Or enqueue jobs through the API with an authenticated user:

```bash
POST /jobs
GET /jobs
POST /jobs/process
```

### Resolve / matching evaluation

Evaluate entity-resolution precision and recall:

```bash
python scripts/evaluate_entity_resolution.py
```

Use a custom labeled dataset:

```bash
python scripts/evaluate_entity_resolution.py --dataset .\\tests\\fixtures\\entity_resolution_eval.json
```

### Option 2: Docker Compose

Use this when you want the project stack to start together.

```bash
docker compose up
```

This starts:

- Neo4j Community Edition
- the PackGraph API
- the synthetic dataset generation and ingestion flow
- optional private-data ingestion from `private_data/`

## Runtime modes

### Local JSON-backed mode

Useful for:

- UI iteration
- demo review without a graph database
- frontend feature work
- local-first portfolio walkthroughs

### Neo4j-backed mode

Useful for:

- live graph traversal
- pathfinding
- relationship previews
- node context retrieval
- query-audit and plan-oriented graph behavior

When `GRAPH_BACKEND=neo4j`, the app writes graph query audit output to `data/runtime/neo4j_query_audit.jsonl`.

## Agent staging and review flow

The chat backend now behaves like a controlled graph assistant without becoming a fully autonomous writer.

- Query responses now include `agent_state_machine`, `agent_tools`, `agent_orchestration`, `investigation_plan`, `evidence_profile`, `missing_evidence`, `project_memory`, `review_candidate`, and `entity_resolution`.
- Local project/session memory is stored in `data/staging/project_memory.json`.
- Human-review candidates are stored in `data/staging/agent_review_candidates.json`.
- Agent audit records are appended to `data/runtime/agent_audit.jsonl`.
- Any merge suggestion, evidence gap, or potential write-back remains staged for human review first.

## Access control and runtime operations

- Users are stored in the runtime SQLite control-plane database rather than only local JSON.
- Passwords are hashed and sessions are issued with expiry windows.
- Role permissions are enforced for review assignment, approval, workspace writes, search saving, contribution review, and job operations.
- Idempotency keys are supported for mutation endpoints such as registration, workspace saves, saved searches, contributions, and job enqueue operations.
- Review decisions now keep immutable history rows in addition to the current candidate state.
- Runtime operational data is separated from graph/domain data so auth, review, and jobs can evolve independently.

## Observability and health

- `GET /health` returns backend mode, private-data activity, runtime DB state, and job summary.
- `GET /health/live` and `GET /health/ready` support container and orchestrator checks.
- `GET /metrics` returns request counters and per-route latency aggregates.
- Structured runtime events are written to `data/runtime/app_events.jsonl`.

## Optional Google ADK scaffold

If you want an ADK-compatible wrapper without making Google tooling part of the default local app:

```bash
pip install -r requirements-adk.txt
```

The optional wrapper lives in `agents/packgraph_lab_agent/agent.py` and exposes read-only tools for classification, readonly graph querying, review-candidate creation, and state-machine inspection.

## Private data mode

- Put confidential or real JSON under `private_data/` or nested subfolders inside it.
- The app discovers these files recursively.
- `GET /private-data/schema` returns field/type summaries without exposing values, filenames, or folder names.
- Natural-language queries can use private data for searches across products, suppliers, materials, locations, grades, and keyword matches.
- Private matches remain read-only until a human-review decision clears any graph write-back.
- Local folder ingest can come either from `.env` defaults or from explicit CLI overrides.
- External-model usage is disabled by default, so the safe local-first path remains the standard runtime.

## Data model overview

The synthetic dataset includes:

- materials
- suppliers
- applications
- regulations
- certifications
- source documents
- test reports
- recycling streams
- regions
- industries
- quarterly snapshots

Typical relationship types include:

- `TARGETS_APPLICATION`
- `SUPPLIED_BY`
- `SUPPLIES`
- `HAS_DOCUMENT`
- `SUBSTITUTES_WITH`
- `RECYCLES_INTO`
- `REVIEWED_UNDER`

## Key API areas

### Product data

- `GET /materials`
- `GET /materials/{id}`
- `GET /suppliers`
- `GET /suppliers/{id}`
- `GET /applications`
- `GET /regulations`
- `GET /regulations/{id}`

### Decision support

- `GET /query/recommendations`
- `POST /query/ask`
- `POST /query/scenario`
- `GET /scenarios/history`
- `GET /compliance/dashboard`
- `GET /graph/relationships`
- `GET /project-memory`
- `GET /review-candidates`
- `GET /review-candidates/summary`

### Workspace and supporting product flows

- `GET /investigations`
- `POST /investigations`
- `GET /search/global`
- `GET /runtime/backends`
- `GET /benchmarks`

## Demo walkthroughs

### Recommendation walkthrough

Ask the workspace for food-safe recommendations and review the structured answer output. Then move into Workbench to compare the returned candidates.

### Evidence walkthrough

Select a material, inspect its provenance and extracted document fields, and use the compliance view to connect the material to supporting evidence and regulations.

### Scenario walkthrough

Run a supplier outage or regulation activation scenario and show how the projected impacts, actions, and scenario history change the decision path.

### Graph walkthrough

Open Intelligence, inspect a node, filter the graph by relationship type, and trace a shortest path between two connected entities.

## Example Cypher files

- [recommend_food_materials.cypher](C:\Users\prana\OneDrive\Documents\Playground\packgraph-lab\queries\recommend_food_materials.cypher)
- [trace_provenance.cypher](C:\Users\prana\OneDrive\Documents\Playground\packgraph-lab\queries\trace_provenance.cypher)
- [risk_screen.cypher](C:\Users\prana\OneDrive\Documents\Playground\packgraph-lab\queries\risk_screen.cypher)

## What makes this project interesting

- It treats packaging intelligence as a connected product problem, not just a dashboard problem.
- It uses synthetic but operational-feeling data so the workflow can be demonstrated safely.
- It separates reviewed query planning from freeform graph generation.
- It supports both local demo behavior and optional live graph execution.
- It includes not only a core workspace, but also research, contribution, and community surfaces around the same domain.

## Current limitations

- The dataset is synthetic and intended for product demonstration, not production decisioning.
- Some domain services still persist portions of demo collaboration state as local runtime JSON while the control plane now uses SQLite.
- The review queue, job workers, and observability layer are local-first operational scaffolds rather than a distributed production platform.
- Neo4j-backed execution is present, but document parsing, alerts, and export workers still have room to become more fully asynchronous and infrastructure-backed.

## Roadmap direction

- Strengthen live Neo4j-backed runtime coverage across more product flows
- Expand document intelligence into richer extraction and evidence linking
- Improve multi-user auth, roles, and saved workspaces
- Increase drilldown depth for suppliers, regulations, and analytics
- Add stronger testing across ingestion, exports, graph flows, and scenario behavior
- Continue modularizing the frontend as the product surfaces grow

## Portfolio use

This project works well as a product-engineering portfolio piece because it demonstrates:

- domain modeling
- graph-oriented thinking
- multi-surface product design
- backend service composition
- local-first developer experience
- documentation and product framing
