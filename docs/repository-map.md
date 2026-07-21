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
  Local developer scripts for generating data, ingesting Neo4j, and benchmarking.
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
- Move repo-wide developer config into a dedicated `config/` folder later if needed.
- Separate seed data from runtime data more explicitly in a future structural refactor.
