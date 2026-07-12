from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.models.schemas import InvestigationCreate, LoginRequest, MaterialCompareRequest, QueryRequest, ScenarioRequest, WorkspaceSaveRequest


def build_router(state) -> APIRouter:
    router = APIRouter()

    @router.get("/materials")
    def list_materials():
        return {"status": "ok", "data": state.repository.list_materials(), "meta": state.repository.manifest["counts"]}

    @router.get("/materials/filter")
    def filter_materials(
        region: str | None = None,
        category: str | None = None,
        compliance_state: str | None = None,
        min_sustainability: int | None = None,
        search: str | None = None,
    ):
        return {
            "status": "ok",
            "data": state.repository.filter_materials(region, category, compliance_state, min_sustainability, search),
        }

    @router.get("/materials/{material_id}")
    def get_material(material_id: str):
        material = state.repository.get_material(material_id)
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")
        return {"status": "ok", "data": material}

    @router.get("/suppliers")
    def list_suppliers():
        return {"status": "ok", "data": state.repository.list_suppliers()}

    @router.get("/applications")
    def list_applications():
        return {"status": "ok", "data": state.repository.list_applications()}

    @router.get("/investigations")
    def list_investigations():
        current_user = state.auth.current_user()
        return {"status": "ok", "data": state.investigations.list(current_user["user_id"] if current_user else None)}

    @router.post("/investigations")
    def create_investigation(payload: InvestigationCreate):
        current_user = state.auth.current_user()
        return {
            "status": "ok",
            "data": state.investigations.create(payload.model_dump(), current_user["user_id"] if current_user else None),
        }

    @router.get("/investigations/{investigation_id}/export.csv")
    def export_investigation_csv(investigation_id: str):
        investigation = state.investigations.get(investigation_id)
        if not investigation:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return Response(
            content=state.exports.investigation_csv(investigation),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{investigation_id}.csv"'},
        )

    @router.get("/investigations/{investigation_id}/export.pdf")
    def export_investigation_pdf(investigation_id: str):
        investigation = state.investigations.get(investigation_id)
        if not investigation:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return Response(
            content=state.exports.investigation_pdf(investigation),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{investigation_id}.pdf"'},
        )

    @router.get("/query/recommendations")
    def recommendations(prioritize_sustainability: bool = False):
        return {"status": "ok", "data": state.repository.recommend_food_packaging(prioritize_sustainability)}

    @router.post("/materials/compare")
    def compare_materials(request: MaterialCompareRequest):
        return {"status": "ok", "data": state.repository.compare_materials(request.material_ids, request.weights)}

    @router.post("/query/ask")
    def ask(request: QueryRequest):
        return {"status": "ok", "data": state.query_engine.ask(request.question, request.options)}

    @router.post("/query/scenario")
    def scenario(request: ScenarioRequest):
        return {
            "status": "ok",
            "data": state.query_engine.run_scenario(
                scenario=request.scenario,
                material_id=request.material_id,
                supplier_id=request.supplier_id,
                options=request.options,
            ),
        }

    @router.get("/runtime/backends")
    def runtime_backends():
        return {"status": "ok", "data": state.repository.backend_status()}

    @router.get("/benchmarks")
    def benchmarks():
        data = state.repository.benchmark_coverage(state.benchmarks())
        return {"status": "ok", "data": data}

    @router.get("/compliance/dashboard")
    def compliance_dashboard():
        watch_count = sum(1 for item in state.repository.materials if item["compliance_state"] == "watch")
        non_compliant_count = sum(1 for item in state.repository.materials if item["compliance_state"] == "non-compliant")
        return {
            "status": "ok",
            "data": {
                "watch_count": watch_count,
                "non_compliant_count": non_compliant_count,
                "at_risk_materials": state.repository.materials_at_risk()[:10],
                "upcoming_regulations": [item for item in state.repository.regulations if not item["active"]][:6],
            },
        }

    @router.get("/graph/relationships")
    def graph_relationships(material_id: str | None = None):
        return {"status": "ok", "data": state.repository.relationship_preview(material_id)}

    @router.get("/graph/subgraph")
    def graph_subgraph(material_id: str):
        return {"status": "ok", "data": state.repository.graph_subgraph(material_id)}

    @router.get("/graph/path")
    def graph_path(source_id: str, target_id: str):
        return {"status": "ok", "data": state.repository.graph_path(source_id, target_id)}

    @router.get("/graph/node-insight")
    def graph_node_insight(node_id: str):
        return {"status": "ok", "data": state.repository.graph_node_insight(node_id)}

    @router.get("/documents/search")
    def documents_search(query: str, material_id: str | None = None):
        return {"status": "ok", "data": state.repository.search_documents(query, material_id)}

    @router.get("/alerts")
    def alerts():
        return {"status": "ok", "data": state.repository.alerts()}

    @router.get("/analytics/overview")
    def analytics_overview():
        return {"status": "ok", "data": state.repository.analytics_overview()}

    @router.post("/auth/login")
    def auth_login(payload: LoginRequest):
        user = state.auth.login(payload.email, payload.password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid demo credentials")
        return {"status": "ok", "data": user}

    @router.get("/auth/session")
    def auth_session():
        return {"status": "ok", "data": state.auth.current_user()}

    @router.get("/workspaces")
    def list_workspaces():
        user = state.auth.current_user()
        return {"status": "ok", "data": state.auth.list_workspaces(user["user_id"] if user else None)}

    @router.post("/workspaces")
    def save_workspace(payload: WorkspaceSaveRequest):
        user = state.auth.current_user()
        if not user:
            raise HTTPException(status_code=401, detail="No active user session")
        return {"status": "ok", "data": state.auth.save_workspace(user["user_id"], payload.model_dump())}

    return router
