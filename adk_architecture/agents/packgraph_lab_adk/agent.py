from __future__ import annotations

import os

from google.adk.agents import Agent

from adk_architecture.tools import get_adk_tools


root_agent = Agent(
    name="packgraph_lab_adk",
    model=os.getenv("PACKGRAPH_ADK_MODEL", "gemini-2.5-flash"),
    description="PackGraph Lab agent that exposes the existing graph, search, scenario, and review flows through Google ADK tools.",
    instruction=(
        "Use the PackGraph tools deterministically. Do not invent direct database writes. "
        "If a request would change graph data or create an ambiguous entity merge, call "
        "the review-candidate tool instead of pretending the change is complete."
    ),
    tools=get_adk_tools(),
)

agent = root_agent
