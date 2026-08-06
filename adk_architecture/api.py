from __future__ import annotations

from fastapi import FastAPI, HTTPException

from adk_architecture.tool_runtime import list_tool_names, run_function_tool
from app.models.schemas import ManualReviewCandidateRequest, QueryRequest, ScenarioRequest


app = FastAPI(title="PackGraph Lab ADK API", version="1.0.0-adk")


def _meta(tool_name: str) -> dict[str, str]:
    return {"mode": "google-adk", "tool": tool_name}


@app.get("/health")
async def health():
    data = await run_function_tool("health_summary")
    return {"status": "ok", "data": data, "meta": _meta("health_summary")}


@app.get("/health/live")
async def health_live():
    data = await run_function_tool("health_summary")
    return {"status": "ok", "data": {"live": True, "backend": data["backend"]}, "meta": _meta("health_summary")}


@app.get("/health/ready")
async def health_ready():
    data = await run_function_tool("health_summary")
    return {"status": "ok", "data": {"ready": True, "runtime_db": data["runtime_db"]}, "meta": _meta("health_summary")}


@app.get("/adk/tools")
async def adk_tools():
    return {"status": "ok", "data": list_tool_names(), "meta": {"mode": "google-adk"}}


@app.get("/materials")
async def materials(limit: int = 200):
    data = await run_function_tool("list_materials", {"limit": limit})
    return {"status": "ok", "data": data, "meta": _meta("list_materials")}


@app.get("/materials/{material_id}")
async def material_detail(material_id: str):
    data = await run_function_tool("get_material", {"material_id": material_id})
    if not data:
        raise HTTPException(status_code=404, detail="Material not found")
    return {"status": "ok", "data": data, "meta": _meta("get_material")}


@app.get("/suppliers")
async def suppliers(region: str | None = None, limit: int = 200):
    data = await run_function_tool("list_suppliers", {"region": region, "limit": limit})
    return {"status": "ok", "data": data, "meta": _meta("list_suppliers")}


@app.post("/query/ask")
async def ask(request: QueryRequest):
    data = await run_function_tool("query_graph", {"question": request.question, "options": request.options})
    return {"status": "ok", "data": data, "meta": _meta("query_graph")}


@app.post("/query/scenario")
async def scenario(request: ScenarioRequest):
    data = await run_function_tool(
        "run_scenario",
        {
            "scenario": request.scenario,
            "material_id": request.material_id,
            "supplier_id": request.supplier_id,
            "options": request.options,
        },
    )
    return {"status": "ok", "data": data, "meta": _meta("run_scenario")}


@app.get("/graph/subgraph")
async def subgraph(material_id: str):
    data = await run_function_tool("graph_subgraph", {"material_id": material_id})
    return {"status": "ok", "data": data, "meta": _meta("graph_subgraph")}


@app.post("/review-candidates/manual")
async def manual_review(payload: ManualReviewCandidateRequest):
    data = await run_function_tool(
        "create_review_candidate",
        {
            "candidate_type": payload.candidate_type,
            "reason": payload.reason,
            "payload": payload.payload,
        },
    )
    return {"status": "ok", "data": data, "meta": _meta("create_review_candidate")}
