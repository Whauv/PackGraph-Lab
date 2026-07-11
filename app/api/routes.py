from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import InvestigationCreate, QueryRequest, ScenarioRequest


def build_router(state) -> APIRouter:
    router = APIRouter()

    @router.get("/materials")
    def list_materials():
        return {"status": "ok", "data": state.repository.list_materials(), "meta": state.repository.manifest["counts"]}

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
        return {"status": "ok", "data": state.investigations.list()}

    @router.post("/investigations")
    def create_investigation(payload: InvestigationCreate):
        return {"status": "ok", "data": state.investigations.create(payload.model_dump())}

    @router.get("/query/recommendations")
    def recommendations(prioritize_sustainability: bool = False):
        return {"status": "ok", "data": state.repository.recommend_food_packaging(prioritize_sustainability)}

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
        data = state.benchmarks()
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

    return router
