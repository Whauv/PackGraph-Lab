# ADR: Query and Frontend Modularization

Date: September 7, 2026

## Context

PackGraph Lab added backend-owned graph chat previews, answer-quality metadata, provisional enrichment requests, source intake, and cross-page chat context. Those features were working, but too much orchestration was collecting in two places:

- `app/services/query_engine.py`
- `web/assets/app.js`

That made the product harder to extend safely because every new query or UI workflow increased the chance of unrelated regressions.

## Decision

Keep the existing public routes and browser boot sequence stable, but move stable responsibilities into smaller modules.

### Backend query services

`QueryEngine` remains the coordinator for `/query/ask`, but delegates specialized work to:

- `query_preview_service.py` for route preview and reviewed-template selection metadata.
- `query_quality_service.py` for answer quality, provenance grouping, lineage checks, and empty-state causes.
- `query_enrichment_service.py` for provisional enrichment requests and `/query/enrich`.
- `workflow_status_service.py` for schema-aware template coverage and supported follow-up prompts.

The goal is not to change query behavior. The goal is to make each response concern independently testable and easier to reason about.

### Frontend controllers

`web/assets/app.js` remains the primary app bootstrap file, but now delegates feature setup to:

- `graph-chat-controller.js`
- `source-intake-controller.js`
- `workbench-controller.js`

This keeps the vanilla JavaScript app intact while making future UI changes less risky.

### Runtime paths

`app/core/runtime_paths.py` centralizes runtime/staging/generated paths so local artifacts have one obvious home and do not leak into source-controlled work by accident.

## Consequences

- Existing API paths remain backward-compatible.
- Frontend modules can be syntax-checked independently.
- Runtime path usage is easier to document and audit.
- Future cleanup can continue incrementally instead of forcing a framework rewrite or large backend rewrite.
