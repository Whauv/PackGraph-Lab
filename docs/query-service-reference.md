# Query Service Reference

PackGraph keeps graph chat deterministic by routing natural-language questions through reviewed templates and local services.

## Key Modules

- `app/services/query_engine.py`: orchestrates preview, ask, enrichment staging, answer quality, provenance, and empty-state metadata.
- `app/services/query_planner.py`: classifies questions into reviewed intents.
- `app/services/query_execution_layer.py`: executes repository-backed read paths.
- `app/services/query_response_builder.py`: builds structured decision panels and workflow recommendations.
- `app/services/query_result_formatter.py`: normalizes rows for scoring and UI rendering.
- `app/services/agent_review.py`: stores human-review candidates and provisional decisions.

## Safety Rules

- `/query/preview` returns safe metadata only.
- `/query/ask` may return an `enrichment_request` when no verified graph rows exist.
- `/query/enrich` stages provisional facts for review and does not write to Neo4j.
- Provisional rows must be marked with `source_type=llm_inferred`, `assertion_kind=LLM_INFERRED`, and `validation_status=pending`.
- Promotion decisions are recorded, but graph mutation is still blocked unless an approved write-back workflow is added.
