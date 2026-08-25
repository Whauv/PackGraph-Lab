# ADR: Structure Stabilization Pass

Date: August 25, 2026

## Context

PackGraph Lab has grown into a broader product shell with graph chat, review workflows, document intelligence, exports, community surfaces, and Neo4j-backed execution. A few core files became orchestration-heavy:

- `app/services/query_engine.py`
- `app/repositories/graph_repository.py`
- `web/assets/app.js`

That made changes slower to review and increased the chance of incidental regressions.

## Decision

We are keeping the public entrypoints stable while splitting responsibilities into smaller support modules.

### Backend query flow

`QueryEngine` remains the runtime entrypoint, but now delegates to:

- `app/services/query_context.py`
- `app/services/query_execution_layer.py`
- `app/services/query_result_formatter.py`
- `app/services/query_response_builder.py`
- `app/services/selected_entity_routing.py`

This keeps the API contract stable while separating:

- context merge and selected-entity hydration
- deterministic execution dispatch
- row normalization and human-readable summaries
- answer-panel and response metadata construction

### Repository support

`LocalGraphRepository` remains the main repository contract, but the implementation now leans on support modules:

- `app/repositories/graph_materials.py`
- `app/repositories/graph_suppliers.py`
- `app/repositories/graph_evidence.py`
- `app/repositories/graph_traversal.py`
- `app/repositories/graph_health.py`

This is intentionally a thin split, not a full repository rewrite.

### Frontend state

The browser app keeps `web/assets/app.js` as the primary boot file, but shared persisted state now starts in:

- `web/assets/modules/app-state.js`

This gives the app one canonical home for:

- active case defaults
- persisted workspace keys
- graph UI persistence
- personal workspace persistence

## Why this approach

- Low migration risk.
- Existing routes, tests, and browser boot sequence remain intact.
- Future work can move feature logic out module-by-module without a large flag day.

## Follow-up

- Continue moving page-specific render/bind logic out of `web/assets/app.js`.
- Add stronger typed API response payloads for major product endpoints.
- Split Neo4j-specific repository logic into support modules similar to the local repository path.
