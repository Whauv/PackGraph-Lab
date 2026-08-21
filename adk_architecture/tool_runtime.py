from __future__ import annotations

import asyncio
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from app.main import state as packgraph_state


def get_packgraph_state():
    """Return the original PackGraph runtime so ADK reuses the same business logic."""
    return packgraph_state


@lru_cache(maxsize=1)
def get_tool_index() -> dict[str, Any]:
    from adk_architecture.tools import get_adk_tools

    return {tool.name: tool for tool in get_adk_tools()}


async def run_function_tool(tool_name: str, args: Mapping[str, Any] | None = None) -> Any:
    tool = get_tool_index()[tool_name]
    return await tool.run_async(args=dict(args or {}), tool_context=None)


def run_function_tool_sync(tool_name: str, args: Mapping[str, Any] | None = None) -> Any:
    tool = get_tool_index()[tool_name]
    sync_runner = getattr(tool, "run_sync", None)
    if callable(sync_runner):
        return sync_runner(args=dict(args or {}), tool_context=None)
    return asyncio.run(tool.run_async(args=dict(args or {}), tool_context=None))


def list_tool_names() -> list[str]:
    return sorted(get_tool_index())
