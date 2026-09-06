# Graph Chat Integration Package

PackGraph's Graph Chat drawer is a reusable right-side assistant surface for graph-backed product pages. It keeps selected entity context, previews safe backend routing, and separates verified KG rows from provisional enrichment requests.

## Frontend Files

- `web/assets/modules/chat-drawer.js`: drawer state, context stack, per-context history, context lock, route preview, answer rendering.
- `web/assets/style.css`: `.graph-chat-*` drawer styling and provisional/lineage warning treatment.
- `web/index.html`: drawer mount point and floating `Graph chat` launcher.

## Mount Example

```html
<div id="graph-chat-overlay" class="graph-chat-overlay" hidden></div>
<aside id="graph-chat-drawer" class="graph-chat-drawer" hidden aria-label="Graph chat drawer"></aside>
<button type="button" id="graph-chat-launcher" class="graph-chat-launcher">Graph chat</button>
<script src="/assets/modules/chat-drawer.js"></script>
```

```js
window.PackGraphChat.init({
  previewRequest: ({ question, context, mode }) => fetch("/query/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, context, mode }),
  }).then((response) => response.json()).then((payload) => payload.data),
  request: ({ question, context, mode }) => fetch("/query/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, context, mode }),
  }).then((response) => response.json()).then((payload) => payload.data),
});
```

## Context Contract

```json
{
  "entity_type": "material",
  "entity_id": "MAT-001",
  "entity_name": "Film A11",
  "metadata": { "category": "film" },
  "history": []
}
```

## Backend Contract

- `POST /query/preview`: returns safe route/template metadata only.
- `POST /query/ask`: returns answer rows plus route preview, answer quality, provenance, empty-state, and enrichment metadata.
- `POST /query/enrich`: stages provisional enrichment for human review without mutating Neo4j.
- `GET /runtime/workflow-status`: returns supported templates and schema blockers.
- `GET /review/provisional`: lists staged provisional enrichment requests.
- `POST /review/provisional/decision`: records promote/reject/needs-more-evidence decisions.

## Provisional Payload

```json
{
  "source": "MAT-001",
  "relationship": "SUPPLIED_BY",
  "target": "missing supplier",
  "confidence": 0.36,
  "evidence": [],
  "query": "show suppliers for this",
  "model": "packgraph-local-enrichment-stub",
  "edge_key": "copyable-id",
  "source_type": "llm_inferred",
  "assertion_kind": "LLM_INFERRED",
  "validation_status": "pending",
  "verification_status": "unverified",
  "promotion_status": "not_promoted"
}
```
