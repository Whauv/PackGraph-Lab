from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.api.route_helpers import (
    cached,
    current_user_or_401,
    get_org_id,
    maybe_current_user,
    maybe_idempotent,
    paginate_records,
    require_permission,
    session_token,
)
from app.models.schemas import (
    ApiEnvelope,
    InvestigationCreate,
    InvestigationUpdate,
    JobEnqueueRequest,
)


def build_ops_router(state) -> APIRouter:
    router = APIRouter()

    @router.get("/health/graph", response_model=ApiEnvelope)
    def graph_health():
        return {"status": "ok", "data": state.repository.graph_health()}

    @router.get("/compliance/dashboard", response_model=ApiEnvelope)
    def compliance_dashboard():
        data = cached(
            state,
            "compliance_dashboard",
            {"scope": "default"},
            lambda: {
                "watch_count": sum(1 for item in state.repository.materials if item["compliance_state"] == "watch"),
                "non_compliant_count": sum(1 for item in state.repository.materials if item["compliance_state"] == "non-compliant"),
                "at_risk_materials": state.repository.materials_at_risk()[:10],
                "upcoming_regulations": [item for item in state.repository.regulations if not item["active"]][:6],
            },
            ttl_seconds=state.settings.response_cache_analytics_ttl_seconds,
        )
        return {"status": "ok", "data": data}

    @router.get("/analytics/overview", response_model=ApiEnvelope)
    def analytics_overview():
        data = cached(
            state,
            "analytics_overview",
            {"scope": "default"},
            lambda: state.repository.analytics_overview(),
            ttl_seconds=state.settings.response_cache_analytics_ttl_seconds,
        )
        return {"status": "ok", "data": data}

    @router.get("/operations/dashboard", response_model=ApiEnvelope)
    def operations_dashboard(request: Request):
        current_user = maybe_current_user(state, request)
        org_id = get_org_id(current_user)
        return {"status": "ok", "data": state.operations.dashboard(org_id=org_id)}

    @router.get("/integrity/report", response_model=ApiEnvelope)
    def integrity_report():
        return {"status": "ok", "data": state.repository.integrity_report()}

    @router.get("/alerts", response_model=ApiEnvelope)
    def alerts(page: int = 1, limit: int = 10):
        rows = cached(
            state,
            "alerts",
            {"scope": "default"},
            lambda: state.repository.alerts(),
            ttl_seconds=state.settings.response_cache_analytics_ttl_seconds,
        )
        page_rows, meta = paginate_records(rows, page=page, limit=limit)
        return {"status": "ok", "data": page_rows, "meta": meta}

    @router.get("/notifications", response_model=ApiEnvelope)
    def notifications(request: Request):
        user = state.auth.current_user(session_token(request))
        def load():
            alert_rows = state.repository.alerts()[:4]
            reviews = state.review_store.list(
                status="pending_human_review",
                org_id=user["org_id"] if user else None,
                limit=4,
            )
            queue = state.contributions.list_queue(org_id=user["org_id"] if user else None)[:4]
            posts = [item for item in state.community.list_posts(org_id=user["org_id"] if user else None) if item.get("moderation_state") == "pending"][:4]
            workspaces = state.auth.list_workspaces(user["user_id"])[:2] if user else []
            scenarios = state.scenario_history.list(user["user_id"])[:2] if user else []
            investigations = state.investigations.list(user["user_id"], org_id=user["org_id"])[:2] if user else []
            return [
                *[
                    {"type": "alert", "title": item["title"], "detail": item["detail"], "tone": item["severity"]}
                    for item in alert_rows
                ],
                *[
                    {"type": "review_request", "title": item["reason"], "detail": f"{item['candidate_type'].replace('_', ' ')} needs approval.", "tone": "warning"}
                    for item in reviews
                ],
                *[
                    {"type": "review", "title": item["title"], "detail": f"Contribution is {item['status'].replace('_', ' ')}.", "tone": "info"}
                    for item in queue
                ],
                *[
                    {"type": "community", "title": item["title"], "detail": f"Moderation state: {item['moderation_state']}.", "tone": "info"}
                    for item in posts
                ],
                *[
                    {"type": "workspace", "title": item["name"], "detail": f"Saved for {item.get('active_tab', 'dashboard')}.", "tone": "success"}
                    for item in workspaces
                ],
                *[
                    {"type": "scenario", "title": item.get("scenario_type", "Scenario").replace("_", " ").title(), "detail": "Scenario result saved to history.", "tone": "info"}
                    for item in scenarios
                ],
                *[
                    {"type": "project", "title": item["title"], "detail": f"{item.get('project_status', 'active')} | due {item.get('due_date') or 'not set'}", "tone": "neutral"}
                    for item in investigations
                ],
            ]
        payload = cached(
            state,
            "notifications",
            {"org_id": user["org_id"] if user else None, "user_id": user["user_id"] if user else None},
            load,
        )
        return {"status": "ok", "data": payload}

    @router.get("/runtime/maintenance", response_model=ApiEnvelope)
    def runtime_maintenance():
        return {"status": "ok", "data": state.runtime_maintenance.summary()}

    @router.post("/runtime/maintenance/cleanup", response_model=ApiEnvelope)
    def runtime_cleanup(request: Request):
        require_permission(state, request, "jobs:process")
        result = state.runtime_maintenance.cleanup()
        return {"status": "ok", "data": result}

    @router.get("/governance/sources", response_model=ApiEnvelope)
    def governance_sources(request: Request):
        current_user = current_user_or_401(state, request)
        return {"status": "ok", "data": state.governance.list_sources(current_user["org_id"])}

    @router.get("/governance/lineage", response_model=ApiEnvelope)
    def governance_lineage(request: Request, entity_type: str, entity_id: str):
        current_user = current_user_or_401(state, request)
        return {"status": "ok", "data": state.lineage.list_for_entity(entity_type, entity_id, current_user["org_id"])}

    @router.get("/jobs", response_model=ApiEnvelope)
    def list_jobs(request: Request, status: str | None = None, page: int = 1, limit: int = 20):
        user = require_permission(state, request, "jobs:view")
        rows = state.jobs.list(status=status, org_id=user["org_id"], limit=500)
        page_rows, meta = paginate_records(rows, page=page, limit=limit)
        meta["summary"] = state.jobs.summary(org_id=user["org_id"])
        return {"status": "ok", "data": page_rows, "meta": meta}

    @router.get("/jobs/{job_id}", response_model=ApiEnvelope)
    def get_job(job_id: str, request: Request):
        user = require_permission(state, request, "jobs:view")
        job = state.jobs.get(job_id)
        if not job or job.get("org_id") != user["org_id"]:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"status": "ok", "data": job}

    @router.post("/jobs", response_model=ApiEnvelope)
    def enqueue_job(payload: JobEnqueueRequest, request: Request):
        user = require_permission(state, request, "jobs:write")
        return maybe_idempotent(
            state,
            request,
            payload.model_dump(),
            lambda: {
                "status": "ok",
                "data": state.jobs.enqueue(
                    job_type=payload.job_type,
                    payload=payload.payload,
                    org_id=user["org_id"],
                    owner_id=user["user_id"],
                    idempotency_key=payload.idempotency_key or request.headers.get("Idempotency-Key"),
                    max_attempts=payload.max_attempts,
                    delay_seconds=payload.delay_seconds,
                ),
            },
        )

    @router.post("/jobs/process", response_model=ApiEnvelope)
    def process_jobs(request: Request, limit: int = 10):
        require_permission(state, request, "jobs:process")
        return {"status": "ok", "data": state.jobs.process_all_available(limit=limit)}

    @router.get("/investigations", response_model=ApiEnvelope)
    def list_investigations(request: Request):
        current_user = state.auth.current_user(session_token(request))
        return {
            "status": "ok",
            "data": state.investigations.list(
                current_user["user_id"] if current_user else None,
                org_id=current_user["org_id"] if current_user else None,
            ),
        }

    @router.post("/investigations", response_model=ApiEnvelope)
    def create_investigation(payload: InvestigationCreate, request: Request):
        current_user = state.auth.current_user(session_token(request))
        return {
            "status": "ok",
            "data": state.investigations.create(
                payload.model_dump(),
                current_user["user_id"] if current_user else None,
                org_id=get_org_id(current_user),
            ),
        }

    @router.get("/investigations/{investigation_id}", response_model=ApiEnvelope)
    def get_investigation(investigation_id: str, request: Request):
        current_user = maybe_current_user(state, request)
        investigation = state.investigations.get(investigation_id, org_id=current_user["org_id"] if current_user else None)
        if not investigation:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return {"status": "ok", "data": investigation}

    @router.patch("/investigations/{investigation_id}", response_model=ApiEnvelope)
    def update_investigation(investigation_id: str, payload: InvestigationUpdate, request: Request):
        current_user = state.auth.current_user(session_token(request))
        investigation = state.investigations.update(
            investigation_id,
            payload.model_dump(),
            current_user["user_id"] if current_user else None,
            org_id=current_user["org_id"] if current_user else None,
        )
        if not investigation:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return {"status": "ok", "data": investigation}

    @router.get("/investigations/{investigation_id}/export.csv")
    def export_investigation_csv(investigation_id: str, request: Request):
        current_user = maybe_current_user(state, request)
        investigation = state.investigations.get(investigation_id, org_id=current_user["org_id"] if current_user else None)
        if not investigation:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return Response(
            content=state.exports.investigation_csv(investigation),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{investigation_id}.csv"'},
        )

    @router.get("/investigations/{investigation_id}/export.pdf")
    def export_investigation_pdf(investigation_id: str, request: Request):
        current_user = maybe_current_user(state, request)
        investigation = state.investigations.get(investigation_id, org_id=current_user["org_id"] if current_user else None)
        if not investigation:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return Response(
            content=state.exports.investigation_pdf(investigation),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{investigation_id}.pdf"'},
        )

    @router.get("/exports/executive-summary.csv")
    def export_executive_summary_csv(material_id: str):
        payload = state.repository.material_export_payload(material_id)
        if not payload:
            raise HTTPException(status_code=404, detail="Material not found")
        return Response(
            content=state.exports.executive_summary_csv(payload),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{material_id}-executive-summary.csv"'},
        )

    @router.get("/exports/executive-summary.pdf")
    def export_executive_summary_pdf(material_id: str):
        payload = state.repository.material_export_payload(material_id)
        if not payload:
            raise HTTPException(status_code=404, detail="Material not found")
        return Response(
            content=state.exports.executive_summary_pdf(payload),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{material_id}-executive-summary.pdf"'},
        )

    @router.get("/exports/compliance-pack.csv")
    def export_compliance_pack_csv(material_id: str):
        payload = state.repository.material_export_payload(material_id)
        if not payload:
            raise HTTPException(status_code=404, detail="Material not found")
        return Response(
            content=state.exports.compliance_pack_csv(payload),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{material_id}-compliance-pack.csv"'},
        )

    @router.get("/exports/compliance-pack.pdf")
    def export_compliance_pack_pdf(material_id: str):
        payload = state.repository.material_export_payload(material_id)
        if not payload:
            raise HTTPException(status_code=404, detail="Material not found")
        return Response(
            content=state.exports.compliance_pack_pdf(payload),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{material_id}-compliance-pack.pdf"'},
        )

    @router.get("/exports/supplier-comparison.csv")
    def export_supplier_comparison_csv(supplier_ids: str):
        ids = [item.strip() for item in supplier_ids.split(",") if item.strip()]
        snapshot = state.repository.supplier_snapshot(ids)
        return Response(
            content=state.exports.supplier_comparison_csv(snapshot),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="supplier-comparison.csv"'},
        )

    @router.get("/exports/supplier-comparison.pdf")
    def export_supplier_comparison_pdf(supplier_ids: str):
        ids = [item.strip() for item in supplier_ids.split(",") if item.strip()]
        snapshot = state.repository.supplier_snapshot(ids)
        return Response(
            content=state.exports.supplier_comparison_pdf(snapshot),
            media_type="application/pdf",
            headers={"Content-Disposition": 'attachment; filename="supplier-comparison.pdf"'},
        )

    return router
