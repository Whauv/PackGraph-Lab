from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.models.schemas import ApiEnvelope, CommunityPostCreate, CommunityReplyCreate, ComponentDiscoveryRequest, ContributionCreate, ContributionReviewRequest, InvestigationCreate, InvestigationUpdate, JobEnqueueRequest, LoginRequest, ManualReviewCandidateRequest, MaterialCompareRequest, ProjectMemoryPatchRequest, QueryAnswerEnvelope, QueryRequest, RegisterRequest, ReviewAssignmentRequest, ReviewCommentRequest, ReviewDecisionRequest, ScenarioRequest, WorkspaceSaveRequest


def build_router(state) -> APIRouter:
    router = APIRouter()

    def _session_token(request: Request) -> str | None:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            return auth_header.split(" ", 1)[1].strip()
        return request.headers.get("X-Session-Token")

    def current_user_or_401(request: Request):
        user = state.auth.current_user(_session_token(request))
        if not user:
            raise HTTPException(status_code=401, detail="No active user session")
        return user

    def maybe_current_user(request: Request):
        return state.auth.current_user(_session_token(request))

    def require_permission(request: Request, permission: str):
        user = current_user_or_401(request)
        if not state.auth.has_permission(user, permission):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        return user

    def maybe_idempotent(request: Request, payload: dict, action):
        idem_key = request.headers.get("Idempotency-Key")
        if not idem_key:
            return action()
        user = maybe_current_user(request)
        org_id = user["org_id"] if user else "ORG-001"
        request_hash = state.idempotency.request_hash(request, str(payload).encode("utf-8"))
        existing = state.idempotency.get(idem_key, org_id=org_id)
        if existing:
            if existing["request_hash"] != request_hash:
                raise HTTPException(status_code=409, detail="Idempotency key reuse with a different payload.")
            return state.idempotency.load_response(existing)
        response_payload = action()
        state.idempotency.store(idem_key, request.method, request.url.path, request_hash, response_payload, org_id=org_id)
        return response_payload

    def paginate_records(records: list[dict], page: int = 1, limit: int = 20) -> tuple[list[dict], dict]:
        safe_limit = max(1, min(limit, 100))
        safe_page = max(1, page)
        start = (safe_page - 1) * safe_limit
        end = start + safe_limit
        sliced = records[start:end]
        return sliced, {
            "page": safe_page,
            "limit": safe_limit,
            "total": len(records),
            "has_next": end < len(records),
            "has_previous": safe_page > 1,
        }

    def cached(namespace: str, payload: dict, loader, ttl_seconds: int | None = None):
        return state.cache.get_or_set(
            f"route:{namespace}",
            payload,
            ttl_seconds=ttl_seconds or state.settings.response_cache_default_ttl_seconds,
            loader=loader,
        )

    @router.get("/materials", response_model=ApiEnvelope)
    def list_materials():
        return {"status": "ok", "data": state.repository.list_materials(), "meta": state.repository.manifest["counts"]}

    @router.get("/materials/filter", response_model=ApiEnvelope)
    def filter_materials(
        region: str | None = None,
        category: str | None = None,
        compliance_state: str | None = None,
        min_sustainability: int | None = None,
        search: str | None = None,
        material_family: str | None = None,
        regulation_id: str | None = None,
        claim_type: str | None = None,
        performance_metric: str | None = None,
        min_performance_score: int | None = None,
        supplier_capability: str | None = None,
    ):
        return {
            "status": "ok",
            "data": state.repository.filter_materials(
                region,
                category,
                compliance_state,
                min_sustainability,
                search,
                material_family,
                regulation_id,
                claim_type,
                performance_metric,
                min_performance_score,
                supplier_capability,
            ),
        }

    @router.get("/materials/{material_id}", response_model=ApiEnvelope)
    def get_material(material_id: str):
        material = state.repository.get_material(material_id)
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")
        return {"status": "ok", "data": material}

    @router.get("/materials/{material_id}/timeline", response_model=ApiEnvelope)
    def material_timeline(material_id: str):
        return {"status": "ok", "data": state.repository.timeline_for_material(material_id)}

    @router.get("/suppliers", response_model=ApiEnvelope)
    def list_suppliers(region: str | None = None, search: str | None = None, page: int = 1, limit: int = 24):
        def load():
            records = state.repository.list_suppliers(region=region)
            if search:
                query = search.lower().strip()
                records = [
                    item for item in records
                    if query in item.get("name", "").lower()
                    or query in item.get("region", "").lower()
                    or query in " ".join(item.get("certifications", [])).lower()
                ]
            return records

        records = cached(
            "suppliers",
            {"region": region, "search": search},
            load,
            ttl_seconds=state.settings.response_cache_graph_ttl_seconds,
        )
        page_rows, meta = paginate_records(records, page=page, limit=limit)
        return {"status": "ok", "data": page_rows, "meta": meta}

    @router.get("/suppliers/regions/summary", response_model=ApiEnvelope)
    def supplier_region_summary():
        return {"status": "ok", "data": state.repository.supplier_region_summary()}

    @router.get("/suppliers/{supplier_id}", response_model=ApiEnvelope)
    def get_supplier(supplier_id: str):
        supplier = state.repository.get_supplier(supplier_id)
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")
        return {"status": "ok", "data": supplier}

    @router.get("/applications", response_model=ApiEnvelope)
    def list_applications():
        return {"status": "ok", "data": state.repository.list_applications()}

    @router.get("/products", response_model=ApiEnvelope)
    def list_products():
        return {"status": "ok", "data": state.repository.list_products()}

    @router.get("/explore/entities", response_model=ApiEnvelope)
    def explore_entities(
        tab: str = "materials",
        search: str | None = None,
        category: str | None = None,
        supplier_id: str | None = None,
        application_id: str | None = None,
        compliance_state: str | None = None,
        min_sustainability: int | None = None,
        region: str | None = None,
        taxonomy: str | None = None,
        page: int = 1,
        limit: int = 24,
    ):
        records = cached(
            "explore_entities",
            {
                "tab": tab,
                "search": search,
                "category": category,
                "supplier_id": supplier_id,
                "application_id": application_id,
                "compliance_state": compliance_state,
                "min_sustainability": min_sustainability,
                "region": region,
                "taxonomy": taxonomy,
            },
            lambda: state.repository.explore_entities(
                tab=tab,
                search=search,
                category=category,
                supplier_id=supplier_id,
                application_id=application_id,
                compliance_state=compliance_state,
                min_sustainability=min_sustainability,
                region=region,
                taxonomy=taxonomy,
            ),
            ttl_seconds=state.settings.response_cache_graph_ttl_seconds,
        )
        page_rows, meta = paginate_records(records, page=page, limit=limit)
        return {"status": "ok", "data": page_rows, "meta": meta}

    @router.get("/explore/autocomplete", response_model=ApiEnvelope)
    def explore_autocomplete(query: str):
        return {"status": "ok", "data": state.repository.explore_autocomplete(query)}

    @router.get("/explore/detail", response_model=ApiEnvelope)
    def explore_detail(entity_type: str, entity_id: str):
        detail = state.repository.explore_detail(entity_type, entity_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Explore entity not found")
        return {"status": "ok", "data": detail}

    @router.get("/regulations", response_model=ApiEnvelope)
    def list_regulations():
        return {"status": "ok", "data": state.repository.list_regulations()}

    @router.get("/regulations/{regulation_id}", response_model=ApiEnvelope)
    def get_regulation(regulation_id: str):
        regulation = state.repository.get_regulation(regulation_id)
        if not regulation:
            raise HTTPException(status_code=404, detail="Regulation not found")
        return {"status": "ok", "data": regulation}

    @router.get("/search/global", response_model=ApiEnvelope)
    def global_search(query: str):
        def load():
            results = state.repository.global_search(query)
            if not results:
                discovered = state.components.discover(query)
                if discovered:
                    record = discovered["record"]
                    results = [
                        {
                            "entity_type": "component",
                            "entity_id": record["component_id"],
                            "title": record["name"],
                            "subtitle": f"{record.get('component_type', 'Web-discovered component')} | cached on {record.get('discovered_at', 'unknown date')}",
                            "meta": f"Stored from {record.get('source_name', 'web discovery')} for future lookups.",
                            "source_url": record.get("source_url", ""),
                            "discovery_state": discovered["discovery_state"],
                        }
                    ]
            return results
        results = cached("global_search", {"query": query}, load, ttl_seconds=state.settings.response_cache_graph_ttl_seconds)
        return {"status": "ok", "data": results}

    @router.get("/components", response_model=ApiEnvelope)
    def list_components():
        return {"status": "ok", "data": state.repository.list_components()}

    @router.get("/components/{component_id}", response_model=ApiEnvelope)
    def get_component(component_id: str):
        component = state.repository.get_component(component_id)
        if not component:
            raise HTTPException(status_code=404, detail="Component not found")
        return {"status": "ok", "data": component}

    @router.post("/components/discover", response_model=ApiEnvelope)
    def discover_component(payload: ComponentDiscoveryRequest):
        discovered = state.components.discover(payload.query)
        if not discovered:
            raise HTTPException(status_code=404, detail="No web-backed component reference could be discovered for this query")
        return {"status": "ok", "data": discovered}

    @router.post("/search/discover", response_model=ApiEnvelope)
    async def discover_from_common_search(
        query: str | None = Form(None),
        image: UploadFile | None = File(None),
    ):
        content = await image.read() if image else None
        payload = state.components.discover_with_related(
            query=query,
            filename=image.filename if image else None,
            content=content,
        )
        if not payload:
            raise HTTPException(status_code=404, detail="No identifiable component or element was found from the current input")
        return {"status": "ok", "data": payload}

    @router.get("/search/command", response_model=ApiEnvelope)
    def command_search(query: str, request: Request):
        current_user = state.auth.current_user(_session_token(request))
        def load():
            results = state.repository.global_search(query)
            workspaces = state.auth.list_workspaces(current_user["user_id"]) if current_user else []
            investigations = state.investigations.list(
                current_user["user_id"] if current_user else None,
                org_id=current_user["org_id"] if current_user else None,
            )
            scenarios = state.scenario_history.list(current_user["user_id"] if current_user else None) if current_user else []
            submissions = [
                item
                for item in state.contributions.list_submissions(org_id=current_user["org_id"] if current_user else None)
                if query.lower() in item.get("title", "").lower()
            ]
            posts = [
                item
                for item in state.community.list_posts(org_id=current_user["org_id"] if current_user else None)
                if query.lower() in item.get("title", "").lower() or query.lower() in item.get("body", "").lower()
            ]
            return {
                "results": results[:10],
                "workspaces": [
                    {"entity_type": "workspace", "entity_id": item["workspace_id"], "title": item["name"], "subtitle": item.get("active_tab", "workspace")}
                    for item in workspaces[:5]
                ],
                "investigations": [
                    {
                        "entity_type": "investigation",
                        "entity_id": item["investigation_id"],
                        "title": item["title"],
                        "subtitle": f"{item.get('project_status', item.get('status', 'open'))} | due {item.get('due_date') or 'not set'}",
                    }
                    for item in investigations[:5]
                    if query.lower() in item.get("title", "").lower() or query.lower() in item.get("notes", "").lower()
                ],
                "scenarios": [
                    {
                        "entity_type": "scenario",
                        "entity_id": item["scenario_id"],
                        "title": item.get("scenario_type", "scenario").replace("_", " ").title(),
                        "subtitle": item.get("created_at", ""),
                    }
                    for item in scenarios[:5]
                    if query.lower() in str(item.get("scenario_type", "")).lower()
                ],
                "contributions": [
                    {"entity_type": "contribution", "entity_id": item["contribution_id"], "title": item["title"], "subtitle": item.get("status", "queued")}
                    for item in submissions[:5]
                ],
                "posts": [
                    {"entity_type": "community_post", "entity_id": item["post_id"], "title": item["title"], "subtitle": item.get("channel_id", "community")}
                    for item in posts[:5]
                ],
            }
        payload = cached(
            "command_search",
            {"query": query, "org_id": current_user["org_id"] if current_user else None},
            load,
            ttl_seconds=state.settings.response_cache_default_ttl_seconds,
        )
        return {"status": "ok", "data": payload}

    @router.get("/private-data/status", response_model=ApiEnvelope)
    def private_data_status():
        return {"status": "ok", "data": state.private_data.private_status()}

    @router.get("/private-data/schema", response_model=ApiEnvelope)
    def private_data_schema():
        return {"status": "ok", "data": state.private_data.inspect_schema()}

    @router.get("/source-intake/sources", response_model=ApiEnvelope)
    def source_intake_sources(request: Request, limit: int = 25):
        current_user = maybe_current_user(request)
        org_id = current_user["org_id"] if current_user else "ORG-001"
        return {"status": "ok", "data": state.source_intake.list_sources(limit=limit, org_id=org_id)}

    @router.get("/source-intake/search", response_model=ApiEnvelope)
    def source_intake_search(request: Request, query: str, limit: int = 8):
        current_user = maybe_current_user(request)
        org_id = current_user["org_id"] if current_user else "ORG-001"
        return {"status": "ok", "data": state.source_intake.search(query, limit=limit, org_id=org_id)}

    @router.post("/source-intake/upload", response_model=ApiEnvelope)
    async def source_intake_upload(
        request: Request,
        file: UploadFile = File(...),
        source_type: str | None = Form(None),
        title: str | None = Form(None),
    ):
        content = await file.read()
        current_user = maybe_current_user(request)
        org_id = current_user["org_id"] if current_user else "ORG-001"
        result = state.source_intake.upload(
            filename=file.filename or "uploaded-source",
            content=content,
            source_type=source_type,
            title=title,
            owner_id=current_user["user_id"] if current_user else None,
            org_id=org_id,
        )
        state.cache.invalidate_prefix("route:source_intake")
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": result}

    @router.get("/investigations", response_model=ApiEnvelope)
    def list_investigations(request: Request):
        current_user = state.auth.current_user(_session_token(request))
        return {
            "status": "ok",
            "data": state.investigations.list(
                current_user["user_id"] if current_user else None,
                org_id=current_user["org_id"] if current_user else None,
            ),
        }

    @router.post("/investigations", response_model=ApiEnvelope)
    def create_investigation(payload: InvestigationCreate, request: Request):
        current_user = state.auth.current_user(_session_token(request))
        return {
            "status": "ok",
            "data": state.investigations.create(
                payload.model_dump(),
                current_user["user_id"] if current_user else None,
                org_id=current_user["org_id"] if current_user else "ORG-001",
            ),
        }

    @router.get("/investigations/{investigation_id}", response_model=ApiEnvelope)
    def get_investigation(investigation_id: str, request: Request):
        current_user = maybe_current_user(request)
        investigation = state.investigations.get(investigation_id, org_id=current_user["org_id"] if current_user else None)
        if not investigation:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return {"status": "ok", "data": investigation}

    @router.patch("/investigations/{investigation_id}", response_model=ApiEnvelope)
    def update_investigation(investigation_id: str, payload: InvestigationUpdate, request: Request):
        current_user = state.auth.current_user(_session_token(request))
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
        current_user = maybe_current_user(request)
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
        current_user = maybe_current_user(request)
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

    @router.get("/query/recommendations", response_model=ApiEnvelope)
    def recommendations(prioritize_sustainability: bool = False):
        return {"status": "ok", "data": state.repository.recommend_food_packaging(prioritize_sustainability)}

    @router.post("/materials/compare", response_model=ApiEnvelope)
    def compare_materials(request: MaterialCompareRequest):
        return {"status": "ok", "data": state.repository.compare_materials(request.material_ids, request.weights)}

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

    @router.post("/query/enrich", response_model=ApiEnvelope)
    def query_enrich(request: QueryRequest):
        return {
            "status": "ok",
            "data": state.query_engine.enrich(
                request.question,
                request.options,
                request.context.model_dump() if request.context else None,
            ),
        }

    @router.get("/runtime/workflow-status", response_model=ApiEnvelope)
    def workflow_status():
        return {"status": "ok", "data": state.query_engine.workflow_status()}

    @router.get("/health/graph", response_model=ApiEnvelope)
    def graph_health():
        return {"status": "ok", "data": state.repository.graph_health()}

    @router.get("/project-memory", response_model=ApiEnvelope)
    def project_memory():
        return {"status": "ok", "data": state.query_engine.project_memory.load()}

    @router.patch("/project-memory", response_model=ApiEnvelope)
    def update_project_memory(payload: ProjectMemoryPatchRequest):
        return {"status": "ok", "data": state.query_engine.project_memory.update(payload.model_dump())}

    @router.get("/review-candidates", response_model=ApiEnvelope)
    def review_candidates(request: Request, status: str | None = None, page: int = 1, limit: int = 24):
        current_user = current_user_or_401(request)
        rows = state.review_store.list(status=status, org_id=current_user["org_id"], limit=500)
        page_rows, meta = paginate_records(rows, page=page, limit=limit)
        return {"status": "ok", "data": page_rows, "meta": meta}

    @router.get("/review-candidates/summary", response_model=ApiEnvelope)
    def review_candidates_summary(request: Request):
        current_user = current_user_or_401(request)
        return {"status": "ok", "data": state.review_store.summary(org_id=current_user["org_id"])}

    @router.get("/review-candidates/{candidate_id}", response_model=ApiEnvelope)
    def review_candidate_detail(candidate_id: str, request: Request):
        current_user = current_user_or_401(request)
        candidate = state.review_store.get(candidate_id, org_id=current_user["org_id"])
        if not candidate:
            raise HTTPException(status_code=404, detail="Review candidate not found")
        return {"status": "ok", "data": candidate}

    @router.get("/review-candidates/{candidate_id}/history", response_model=ApiEnvelope)
    def review_candidate_history(candidate_id: str, request: Request):
        user = require_permission(request, "review:assign")
        candidate = state.review_store.get(candidate_id, org_id=user["org_id"])
        if not candidate:
            raise HTTPException(status_code=404, detail="Review candidate not found")
        return {"status": "ok", "data": state.review_store.history(candidate_id, org_id=user["org_id"])}

    @router.post("/review-candidates/{candidate_id}/assign", response_model=ApiEnvelope)
    def assign_review_candidate(candidate_id: str, payload: ReviewAssignmentRequest, request: Request):
        actor = require_permission(request, "review:assign")
        candidate = state.review_store.assign(candidate_id, payload.reviewer_id, actor["user_id"], actor["org_id"])
        if not candidate:
            raise HTTPException(status_code=404, detail="Review candidate not found")
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": candidate}

    @router.post("/review-candidates/{candidate_id}/comment", response_model=ApiEnvelope)
    def comment_review_candidate(candidate_id: str, payload: ReviewCommentRequest, request: Request):
        actor = current_user_or_401(request)
        candidate = state.review_store.comment(candidate_id, actor["user_id"], payload.comment, actor["org_id"])
        if not candidate:
            raise HTTPException(status_code=404, detail="Review candidate not found")
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": candidate}

    @router.post("/review-candidates/{candidate_id}/decision", response_model=ApiEnvelope)
    def decide_review_candidate(candidate_id: str, payload: ReviewDecisionRequest, request: Request):
        actor = require_permission(request, "review:approve")
        candidate = state.review_store.decide(candidate_id, actor["user_id"], payload.status, payload.comment, payload.metadata, actor["org_id"])
        if not candidate:
            raise HTTPException(status_code=404, detail="Review candidate not found")
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": candidate}

    @router.post("/review-candidates/manual", response_model=ApiEnvelope)
    def create_manual_review_candidate(payload: ManualReviewCandidateRequest, request: Request):
        actor = current_user_or_401(request)
        candidate = state.review_store.create(
            payload.candidate_type,
            payload.reason,
            {
                **payload.payload,
                "submitted_by": actor["user_id"],
                "submitted_by_name": actor["name"],
            },
            org_id=actor["org_id"],
        )
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": candidate}

    @router.get("/review-candidates/export", response_model=ApiEnvelope)
    def export_review_candidates(output: str, request: Request, include_raw_props: bool = False):
        user = require_permission(request, "review:assign")
        return {
            "status": "ok",
            "data": state.review_store.export_pending(Path(output), org_id=user["org_id"], include_raw_props=include_raw_props),
        }

    @router.post("/review-candidates/import", response_model=ApiEnvelope)
    def import_review_candidates(request: Request, input_path: str, apply: bool = False):
        user = current_user_or_401(request)
        if apply:
            require_permission(request, "review:approve")
        return {"status": "ok", "data": state.review_store.import_reviewed_decisions(Path(input_path), apply=apply, org_id=user["org_id"])}

    @router.post("/query/scenario", response_model=ApiEnvelope)
    def scenario(request: ScenarioRequest, http_request: Request):
        current_user = state.auth.current_user(_session_token(http_request))
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
        return {
            "status": "ok",
            "data": result,
        }

    @router.get("/scenarios/history", response_model=ApiEnvelope)
    def scenario_history(request: Request):
        current_user = state.auth.current_user(_session_token(request))
        return {"status": "ok", "data": state.scenario_history.list(current_user["user_id"] if current_user else None)}

    @router.get("/runtime/backends", response_model=ApiEnvelope)
    def runtime_backends():
        return {"status": "ok", "data": state.repository.backend_status()}

    @router.get("/benchmarks", response_model=ApiEnvelope)
    def benchmarks():
        data = state.repository.benchmark_coverage(state.benchmarks())
        return {"status": "ok", "data": data}

    @router.get("/compliance/dashboard", response_model=ApiEnvelope)
    def compliance_dashboard():
        data = cached(
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

    @router.get("/graph/relationships", response_model=ApiEnvelope)
    def graph_relationships(material_id: str | None = None):
        return {"status": "ok", "data": state.repository.relationship_preview(material_id)}

    @router.get("/graph/subgraph", response_model=ApiEnvelope)
    def graph_subgraph(material_id: str):
        data = cached(
            "graph_subgraph",
            {"material_id": material_id},
            lambda: state.repository.graph_subgraph(material_id),
            ttl_seconds=state.settings.response_cache_graph_ttl_seconds,
        )
        return {"status": "ok", "data": data}

    @router.get("/graph/path", response_model=ApiEnvelope)
    def graph_path(source_id: str, target_id: str):
        return {"status": "ok", "data": state.repository.graph_path(source_id, target_id)}

    @router.get("/graph/node-insight", response_model=ApiEnvelope)
    def graph_node_insight(node_id: str):
        data = cached(
            "graph_node_insight",
            {"node_id": node_id},
            lambda: state.repository.graph_node_insight(node_id),
            ttl_seconds=state.settings.response_cache_graph_ttl_seconds,
        )
        return {"status": "ok", "data": data}

    @router.get("/documents/search", response_model=ApiEnvelope)
    def documents_search(query: str, material_id: str | None = None, page: int = 1, limit: int = 20):
        rows = cached(
            "documents_search",
            {"query": query, "material_id": material_id},
            lambda: state.repository.search_documents(query, material_id),
            ttl_seconds=state.settings.response_cache_graph_ttl_seconds,
        )
        page_rows, meta = paginate_records(rows, page=page, limit=limit)
        return {"status": "ok", "data": page_rows, "meta": meta}

    @router.get("/documents/{document_id}", response_model=ApiEnvelope)
    def document_detail(document_id: str):
        detail = state.repository.document_detail(document_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"status": "ok", "data": detail}

    @router.post("/documents/upload", response_model=ApiEnvelope)
    async def documents_upload(
        request: Request,
        file: UploadFile = File(...),
        document_type: str = Form(...),
        material_id: str = Form(...),
        supplier_id: str | None = Form(None),
        title: str | None = Form(None),
    ):
        content = await file.read()
        current_user = state.auth.current_user(_session_token(request))
        org_id = current_user["org_id"] if current_user else "ORG-001"
        uploaded_at = datetime.now(UTC).isoformat()
        source = state.governance.register_source(
            org_id=org_id,
            source_type=document_type,
            source_family="uploaded-document",
            display_name=title or file.filename or "Uploaded evidence",
            connector_name="local-upload",
            parser_name=state.settings.ingest_parser_name,
            parser_version=state.settings.ingest_parser_version,
            trust_score=0.74,
            pii_risk_level="medium",
        )
        result = state.documents.upload(
            filename=file.filename or "uploaded-file",
            content=content,
            document_type=document_type,
            material_id=material_id,
            supplier_id=supplier_id,
            title=title,
            owner_id=current_user["user_id"] if current_user else None,
            org_id=org_id,
            provenance={"source_id": source["source_id"], "source_family": source["source_family"], "trust_score": source["trust_score"]},
            retention=state.governance.retention_preview(org_id, uploaded_at),
        )
        field_payload = result["record"].get("field_confidence", [])
        state.lineage.record_lineage(
            org_id=org_id,
            source_id=source["source_id"],
            artifact_id=result["artifact"]["artifact_id"],
            entity_type=result["kind"],
            entity_id=result["record"].get("document_id") or result["record"].get("report_id"),
            field_name="summary",
            citation_span=result["record"].get("extraction_summary"),
            field_confidence=result["record"].get("extraction_confidence"),
            metadata={"material_id": material_id, "supplier_id": supplier_id, "field_payload": field_payload},
        )
        result["provenance_viewer"] = state.lineage.provenance_viewer_payload(
            org_id=org_id,
            source_id=source["source_id"],
            artifact_id=result["artifact"]["artifact_id"],
            extracted_fields=field_payload,
            summary=result["record"].get("extraction_summary", ""),
            uploaded_at=result["artifact"]["uploaded_at"],
        )
        state.cache.invalidate_prefix("route:documents_search")
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": result}

    @router.get("/alerts", response_model=ApiEnvelope)
    def alerts(page: int = 1, limit: int = 10):
        rows = cached(
            "alerts",
            {"scope": "default"},
            lambda: state.repository.alerts(),
            ttl_seconds=state.settings.response_cache_analytics_ttl_seconds,
        )
        page_rows, meta = paginate_records(rows, page=page, limit=limit)
        return {"status": "ok", "data": page_rows, "meta": meta}

    @router.get("/analytics/overview", response_model=ApiEnvelope)
    def analytics_overview():
        data = cached(
            "analytics_overview",
            {"scope": "default"},
            lambda: state.repository.analytics_overview(),
            ttl_seconds=state.settings.response_cache_analytics_ttl_seconds,
        )
        return {"status": "ok", "data": data}

    @router.get("/operations/dashboard", response_model=ApiEnvelope)
    def operations_dashboard(request: Request):
        current_user = maybe_current_user(request)
        org_id = current_user["org_id"] if current_user else "ORG-001"
        return {"status": "ok", "data": state.operations.dashboard(org_id=org_id)}

    @router.get("/integrity/report", response_model=ApiEnvelope)
    def integrity_report():
        return {"status": "ok", "data": state.repository.integrity_report()}

    @router.post("/auth/login", response_model=ApiEnvelope)
    def auth_login(payload: LoginRequest):
        user = state.auth.login(payload.email, payload.password)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {"status": "ok", "data": user}

    @router.post("/auth/register", response_model=ApiEnvelope)
    def auth_register(payload: RegisterRequest, request: Request):
        def create():
            try:
                user = state.auth.register(payload.name, payload.email, payload.password, payload.role_id)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return {"status": "ok", "data": user}
        return maybe_idempotent(request, payload.model_dump(), create)

    @router.post("/auth/logout", response_model=ApiEnvelope)
    def auth_logout(request: Request):
        state.auth.logout(_session_token(request))
        return {"status": "ok", "data": {"logged_out": True}}

    @router.get("/auth/session", response_model=ApiEnvelope)
    def auth_session(request: Request):
        return {"status": "ok", "data": state.auth.current_user(_session_token(request))}

    @router.get("/auth/roles", response_model=ApiEnvelope)
    def auth_roles():
        return {"status": "ok", "data": state.auth.list_roles()}

    @router.get("/auth/organizations", response_model=ApiEnvelope)
    def auth_organizations():
        return {"status": "ok", "data": state.auth.list_organizations()}

    @router.get("/workspaces", response_model=ApiEnvelope)
    def list_workspaces(request: Request):
        user = state.auth.current_user(_session_token(request))
        return {"status": "ok", "data": state.auth.list_workspaces(user["user_id"] if user else None)}

    @router.post("/workspaces", response_model=ApiEnvelope)
    def save_workspace(payload: WorkspaceSaveRequest, request: Request):
        user = require_permission(request, "workspaces:write")
        response = maybe_idempotent(
            request,
            payload.model_dump(),
            lambda: {"status": "ok", "data": state.auth.save_workspace(user["user_id"], payload.model_dump())},
        )
        state.cache.invalidate_prefix("route:notifications")
        return response

    @router.get("/searches", response_model=ApiEnvelope)
    def list_saved_searches(request: Request):
        user = current_user_or_401(request)
        return {"status": "ok", "data": state.auth.list_saved_searches(user["user_id"])}

    @router.post("/searches", response_model=ApiEnvelope)
    def save_search(payload: dict, request: Request):
        user = require_permission(request, "search:save")
        response = maybe_idempotent(
            request,
            payload,
            lambda: {"status": "ok", "data": state.auth.save_search(user["user_id"], payload)},
        )
        state.cache.invalidate_prefix("route:notifications")
        return response

    @router.get("/contributions/roles", response_model=ApiEnvelope)
    def contribution_roles():
        return {"status": "ok", "data": state.contributions.list_roles()}

    @router.get("/contributions", response_model=ApiEnvelope)
    def list_contributions(request: Request):
        current_user = maybe_current_user(request)
        org_id = current_user["org_id"] if current_user else "ORG-001"
        return {
            "status": "ok",
            "data": {
                "submissions": state.contributions.list_submissions(org_id=org_id),
                "status_summary": state.contributions.status_summary(org_id=org_id),
                "review_queue": state.contributions.list_queue(org_id=org_id),
            },
        }

    @router.post("/contributions", response_model=ApiEnvelope)
    def create_contribution(payload: ContributionCreate, request: Request):
        current_user = require_permission(request, "contributions:write")
        if payload.related_entity_type or payload.related_entity_id:
            validation = state.repository.validate_entity_reference(payload.related_entity_type, payload.related_entity_id)
            if not validation["valid"]:
                raise HTTPException(status_code=400, detail=validation["message"])
        submitted_by = current_user["name"]
        response = maybe_idempotent(
            request,
            payload.model_dump(),
            lambda: {"status": "ok", "data": state.contributions.create(payload.model_dump(), submitted_by, org_id=current_user["org_id"])},
        )
        state.cache.invalidate_prefix("route:notifications")
        return response

    @router.post("/contributions/{contribution_id}/review", response_model=ApiEnvelope)
    def review_contribution(contribution_id: str, payload: ContributionReviewRequest, request: Request):
        reviewer = require_permission(request, "contributions:review")
        record = state.contributions.review(contribution_id, payload.status, reviewer["name"], payload.reviewer_note, org_id=reviewer["org_id"])
        if not record:
            raise HTTPException(status_code=404, detail="Contribution not found")
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": record}

    @router.get("/jobs", response_model=ApiEnvelope)
    def list_jobs(request: Request, status: str | None = None, page: int = 1, limit: int = 20):
        user = require_permission(request, "jobs:view")
        rows = state.jobs.list(status=status, org_id=user["org_id"], limit=500)
        page_rows, meta = paginate_records(rows, page=page, limit=limit)
        meta["summary"] = state.jobs.summary(org_id=user["org_id"])
        return {"status": "ok", "data": page_rows, "meta": meta}

    @router.get("/jobs/{job_id}", response_model=ApiEnvelope)
    def get_job(job_id: str, request: Request):
        user = require_permission(request, "jobs:view")
        job = state.jobs.get(job_id)
        if not job or job.get("org_id") != user["org_id"]:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"status": "ok", "data": job}

    @router.post("/jobs", response_model=ApiEnvelope)
    def enqueue_job(payload: JobEnqueueRequest, request: Request):
        user = require_permission(request, "jobs:write")
        return maybe_idempotent(
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
        require_permission(request, "jobs:process")
        return {"status": "ok", "data": state.jobs.process_all_available(limit=limit)}

    @router.get("/community/channels", response_model=ApiEnvelope)
    def community_channels(request: Request):
        current_user = maybe_current_user(request)
        return {"status": "ok", "data": state.community.list_channels(org_id=current_user["org_id"] if current_user else "ORG-001")}

    @router.get("/community/posts", response_model=ApiEnvelope)
    def community_posts(
        request: Request,
        channel_id: str | None = None,
        moderation_state: str | None = None,
        related_entity_id: str | None = None,
        page: int = 1,
        limit: int = 12,
    ):
        current_user = maybe_current_user(request)
        org_id = current_user["org_id"] if current_user else "ORG-001"
        rows = cached(
            "community_posts",
            {
                "channel_id": channel_id,
                "moderation_state": moderation_state,
                "related_entity_id": related_entity_id,
                "org_id": org_id,
            },
            lambda: state.community.list_posts(channel_id, moderation_state, related_entity_id, org_id),
        )
        page_rows, meta = paginate_records(rows, page=page, limit=limit)
        return {"status": "ok", "data": page_rows, "meta": meta}

    @router.get("/community/posts/{post_id}", response_model=ApiEnvelope)
    def community_post_detail(post_id: str, request: Request):
        current_user = maybe_current_user(request)
        post = state.community.get_post(post_id, current_user["org_id"] if current_user else "ORG-001")
        if not post:
            raise HTTPException(status_code=404, detail="Community post not found")
        return {"status": "ok", "data": post}

    @router.post("/community/posts", response_model=ApiEnvelope)
    def create_community_post(payload: CommunityPostCreate, request: Request):
        current_user = require_permission(request, "community:write")
        author_name = current_user["name"]
        response = {
            "status": "ok",
            "data": state.community.create_post(payload.model_dump(), author_name, current_user["role_title"], 68, current_user["org_id"]),
        }
        state.cache.invalidate_prefix("route:community_posts")
        state.cache.invalidate_prefix("route:notifications")
        return response

    @router.post("/community/posts/{post_id}/upvote", response_model=ApiEnvelope)
    def upvote_community_post(post_id: str, request: Request):
        current_user = current_user_or_401(request)
        post = state.community.upvote(post_id, current_user["org_id"])
        if not post:
            raise HTTPException(status_code=404, detail="Community post not found")
        state.cache.invalidate_prefix("route:community_posts")
        return {"status": "ok", "data": post}

    @router.post("/community/posts/{post_id}/save", response_model=ApiEnvelope)
    def save_community_post(post_id: str, request: Request):
        current_user = current_user_or_401(request)
        post = state.community.save_post(post_id, current_user["org_id"])
        if not post:
            raise HTTPException(status_code=404, detail="Community post not found")
        state.cache.invalidate_prefix("route:community_posts")
        return {"status": "ok", "data": post}

    @router.post("/community/posts/{post_id}/reply", response_model=ApiEnvelope)
    def reply_community_post(post_id: str, payload: CommunityReplyCreate, request: Request):
        current_user = require_permission(request, "community:write")
        post = state.community.add_reply(post_id, payload.body, current_user["name"], current_user["role_title"], current_user["org_id"])
        if not post:
            raise HTTPException(status_code=404, detail="Community post not found")
        state.cache.invalidate_prefix("route:community_posts")
        return {"status": "ok", "data": post}

    @router.post("/community/posts/{post_id}/pin", response_model=ApiEnvelope)
    def pin_community_post(post_id: str, request: Request):
        current_user = require_permission(request, "community:pin")
        post = state.community.pin(post_id, current_user["org_id"])
        if not post:
            raise HTTPException(status_code=404, detail="Community post not found")
        state.cache.invalidate_prefix("route:community_posts")
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": post}

    @router.get("/notifications", response_model=ApiEnvelope)
    def notifications(request: Request):
        user = state.auth.current_user(_session_token(request))
        def load():
            alerts = state.repository.alerts()[:4]
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
                    for item in alerts
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
            "notifications",
            {"org_id": user["org_id"] if user else None, "user_id": user["user_id"] if user else None},
            load,
        )
        return {
            "status": "ok",
            "data": payload,
        }

    @router.get("/runtime/maintenance", response_model=ApiEnvelope)
    def runtime_maintenance():
        return {"status": "ok", "data": state.runtime_maintenance.summary()}

    @router.post("/runtime/maintenance/cleanup", response_model=ApiEnvelope)
    def runtime_cleanup(request: Request):
        require_permission(request, "jobs:process")
        result = state.runtime_maintenance.cleanup()
        return {"status": "ok", "data": result}

    @router.get("/governance/sources", response_model=ApiEnvelope)
    def governance_sources(request: Request):
        current_user = current_user_or_401(request)
        return {"status": "ok", "data": state.governance.list_sources(current_user["org_id"])}

    @router.get("/governance/lineage", response_model=ApiEnvelope)
    def governance_lineage(request: Request, entity_type: str, entity_id: str):
        current_user = current_user_or_401(request)
        return {"status": "ok", "data": state.lineage.list_for_entity(entity_type, entity_id, current_user["org_id"])}

    return router
