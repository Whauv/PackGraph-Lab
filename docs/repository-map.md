# Repository Map

This file is the low-risk structure guide for PackGraph Lab. It does not change runtime paths. It gives the repo a clearer mental model so future updates are easier to place and easier to review.

## Top-level map

- `app/`
  FastAPI backend code.
- `data/`
  Synthetic seed data plus local runtime state written by the app.
- `docs/`
  Architecture notes, repository guidance, and change tracking.
- `queries/`
  Example Cypher queries and graph-oriented reference snippets.
- `scripts/`
  Local developer scripts for generating data, ingesting Neo4j, health checks, review workflows, and validation.
- `tests/`
  Backend-focused automated tests.
- `web/`
  Product UI, landing page, and frontend assets.

## What belongs where

### `app/`

Use this folder for backend runtime code only.

- `api/`
  Route registration and API surface.
- `core/`
  Config, app wiring, and shared backend setup.
- `models/`
  Schemas and typed payload definitions.
- `repositories/`
  Data-access and graph-query implementations.
- `services/`
  Product logic such as scenarios, exports, auth, document intelligence, and community flows.

Recent structural anchors:

- `core/runtime_paths.py`
  Central helper for generated, runtime, staging, report, ingest-state, memory, and review-candidate paths.
- `services/query_context.py`
  Selected-entity merge and question hydration helpers.
- `services/query_execution_layer.py`
  Deterministic query intent dispatch.
- `services/query_preview_service.py`
  Safe backend-owned route preview for `/query/preview`.
- `services/query_quality_service.py`
  Answer-quality metadata, provenance split, lineage warnings, and empty-state cause detection.
- `services/query_enrichment_service.py`
  Provisional enrichment request construction for `/query/enrich` without direct graph mutation.
- `services/query_result_formatter.py`
  Human-readable summaries and row normalization.
- `services/query_response_builder.py`
  Classifier metadata, answer panel, and review-gate assembly.
- `services/selected_entity_routing.py`
  Shared selected-entity routing helpers.
- `services/workflow_status_service.py`
  Schema-aware template coverage and Graph Chat workflow status.
- `repositories/graph_*.py`
  Focused support modules for materials, suppliers, evidence, traversal, and health logic.

### `data/`

Treat this as two buckets even though the current runtime paths stay the same:

- `data/generated/`
  Regenerable synthetic demo seed files. Safe to rebuild.
- `data/runtime/`
  Local app state and temporary outputs. These files change often during demos and development.

If a file is regenerated or user-session-specific, it should usually live under `data/runtime/` and often be ignored in Git.

### `web/`

Use this folder for frontend runtime assets only.

- `landing.html`
  Entry / marketing page.
- `index.html`
  Product application shell.
- `assets/`
  Shared CSS, JS, images, and page modules.
- `assets/modules/`
  Page- or feature-level frontend modules.

Recent structural anchors:

- `assets/modules/shared-ui.js`
  Shared UI primitives and guided-tour helpers.
- `assets/modules/app-state.js`
  Shared persisted browser state defaults and storage keys.
- `assets/modules/graph-chat-controller.js`
  Graph Chat drawer bootstrapping, backend preview wiring, and workflow-status loading.
- `assets/modules/source-intake-controller.js`
  Source upload, schema-profile rendering, and uploaded-source list behavior.
- `assets/modules/workbench-controller.js`
  Workbench form binding for comparison, evidence upload, scenarios, graph paths, and case persistence.
- `assets/app.js`
  Main boot file that now composes shared modules instead of owning every feature controller directly.

## Source-controlled vs local-only paths

Source-controlled:

- `app/`, `docs/`, `queries/`, `scripts/`, `tests/`, and `web/`
- stable synthetic seed fixtures that are intentionally checked in
- `.env.example` and other non-secret configuration examples

Local-only:

- `.env`
- `private_data/`
- Python caches such as `__pycache__/` and `*.pyc`
- `data/runtime/` state, caches, audit logs, reports, and local DB files
- runtime-generated manifest or smoke-test output files

When in doubt, runtime/session/user-specific files should go under a runtime path from `app/core/runtime_paths.py` and should not be committed.

## Recommended update workflow

When adding work, place it by intent:

1. Backend behavior changes:
   edit `app/`, `tests/`, and maybe `scripts/`.
2. Frontend behavior or layout changes:
   edit `web/`.
3. Demo dataset changes:
   edit generator logic in `app/services/data_generator.py` and regenerate `data/generated/`.
4. Runbook, architecture, or planning updates:
   edit `docs/`.

## Review-friendly commit grouping

Try to keep changes grouped by area:

- Backend: `app/`, `tests/`, `scripts/`
- Frontend: `web/`
- Data/runtime: `data/`
- Documentation: `docs/`, `README.md`

This makes diffs easier to scan and makes regressions easier to trace.

## Low-risk future cleanup ideas

- Add `docs/changes/` entries for notable milestones.
- Split large frontend files into more feature-focused modules.
- Keep extracting page controllers from `web/assets/app.js` into `web/assets/modules/`.
- Move repo-wide developer config into a dedicated `config/` folder later if needed.
- Separate seed data from runtime data more explicitly in a future structural refactor.
