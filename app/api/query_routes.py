from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.route_helpers import session_token
from app.models.schemas import (
    ApiEnvelope,
    ProjectMemoryPatchRequest,
    QueryAnswerEnvelope,
    QueryEnrichmentEnvelope,
    QueryPreviewEnvelope,
    QueryRequest,
    ScenarioRequest,
    WorkflowStatusEnvelope,
)


def build_query_router(state) -> APIRouter:
    router = APIRouter()

    @router.get("/query/recommendations", response_model=ApiEnvelope)
    def recommendations(prioritize_sustainability: bool = False):
        return {"status": "ok", "data": state.repository.recommend_food_packaging(prioritize_sustainability)}

    @router.post("/query/ask", response_model=QueryAnswerEnvelope)
    def ask(request: QueryRequest):
        return {
            "status": "ok",
            "data": state.query_engine.ask(
                request.question,
                request.options,
                request.context.model_dump() if request.context else None,
                request.mode,
            ),
        }

    @router.post("/query/preview", response_model=QueryPreviewEnvelope)
    def query_preview(request: QueryRequest):
        return {
            "status": "ok",
            "data": state.query_engine.preview(
                request.question,
                request.options,
                request.context.model_dump() if request.context else None,
                request.mode,
            ),
        }

    @router.post("/query/enrich", response_model=QueryEnrichmentEnvelope)
    def query_enrich(request: QueryRequest):
        return {
            "status": "ok",
            "data": state.query_engine.enrich(
                request.question,
                request.options,
                request.context.model_dump() if request.context else None,
            ),
        }

    @router.get("/runtime/workflow-status", response_model=WorkflowStatusEnvelope)
    def workflow_status():
        return {"status": "ok", "data": state.query_engine.workflow_status()}

    @router.post("/query/scenario", response_model=ApiEnvelope)
    def scenario(request: ScenarioRequest, http_request: Request):
        current_user = state.auth.current_user(session_token(http_request))
        result = state.query_engine.run_scenario(
            scenario=request.scenario,
            material_id=request.material_id,
            supplier_id=request.supplier_id,
            options=request.options,
        )
        state.scenario_history.save(
            scenario_type=request.scenario,
            material_id=request.material_id,
            supplier_id=request.supplier_id,
            options=request.options,
            result=result,
            owner_id=current_user["user_id"] if current_user else None,
        )
        return {"status": "ok", "data": result}

    @router.get("/scenarios/history", response_model=ApiEnvelope)
    def scenario_history(request: Request):
        current_user = state.auth.current_user(session_token(request))
        return {"status": "ok", "data": state.scenario_history.list(current_user["user_id"] if current_user else None)}

    @router.get("/private-data/status", response_model=ApiEnvelope)
    def private_data_status():
        return {"status": "ok", "data": state.private_data.private_status()}

    @router.get("/private-data/schema", response_model=ApiEnvelope)
    def private_data_schema():
        return {"status": "ok", "data": state.private_data.inspect_schema()}

    @router.get("/project-memory", response_model=ApiEnvelope)
    def project_memory():
        return {"status": "ok", "data": state.query_engine.project_memory.load()}

    @router.patch("/project-memory", response_model=ApiEnvelope)
    def update_project_memory(payload: ProjectMemoryPatchRequest):
        return {"status": "ok", "data": state.query_engine.project_memory.update(payload.model_dump())}

    return router
