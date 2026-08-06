# PackGraph Lab ADK Architecture

This folder adds a second, parallel Google ADK-dependent runtime for PackGraph Lab without replacing the original app.

## What stays the same

- The original FastAPI app in `app/main.py` remains the main implementation.
- Existing repository, query engine, review workflow, governance, and runtime data handling stay in the original codebase.
- The ADK layer reuses those services instead of duplicating business rules.

## What ADK owns

- `api.py`: a separate FastAPI surface that executes PackGraph behavior through Google ADK `FunctionTool` wrappers.
- `tools.py`: the ADK tool catalog.
- `tool_runtime.py`: the bridge between ADK tools and the original PackGraph runtime.
- `agents/packgraph_lab_adk/agent.py`: the root ADK agent for CLI and web testing.
- `run_adk_tool_smoke.py`: a local smoke test for `FunctionTool.run_async(...)`.

## Run the original app

```bash
uvicorn app.main:app --reload
```

Default app URL: `http://127.0.0.1:8000`

## Run the ADK FastAPI app

```bash
uvicorn adk_architecture.api:app --reload --port 8001
```

ADK API URL: `http://127.0.0.1:8001`

## Run the ADK smoke check

```bash
python -m adk_architecture.run_adk_tool_smoke
python -m adk_architecture.run_adk_tool_smoke --check-db
```

## Run the ADK CLI

From the `adk_architecture/agents` directory:

```bash
adk run packgraph_lab_adk
```

## Run the ADK web UI

From the `adk_architecture/agents` directory:

```bash
adk web --port 8001
```

ADK Web is for development/debugging, not production use.

## Notes

- Writes should go through the review-candidate tool instead of direct mutation.
- The ADK layer mirrors selected PackGraph routes like health, materials, suppliers, graph query, scenario execution, and manual review staging.
- Private data is not copied into this folder; the ADK layer reuses the original runtime.
