from __future__ import annotations

import argparse
import asyncio
import json

from adk_architecture.tool_runtime import run_function_tool


async def _run(check_db: bool) -> dict:
    results: dict[str, object] = {}
    results["health"] = await run_function_tool("health_summary")
    results["classification"] = await run_function_tool(
        "classify_question",
        {"question": "Find recyclable substitutes for Film A11 with evidence."},
    )
    if check_db:
        results["query"] = await run_function_tool(
            "query_graph",
            {"question": "Find recyclable substitutes for Film A11 with evidence.", "options": {}},
        )
    else:
        results["query"] = {"status": "skipped", "reason": "Pass --check-db to execute the graph-backed question path."}
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-check the PackGraph Google ADK tool layer.")
    parser.add_argument("--check-db", action="store_true", help="Also run a graph-backed PackGraph question through the ADK FunctionTool.")
    args = parser.parse_args()
    payload = asyncio.run(_run(args.check_db))
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
