from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.api.route_helpers import (
    cached,
    maybe_current_user,
    get_org_id,
    paginate_records,
    session_token,
)
from app.models.schemas import ApiEnvelope, ComponentDiscoveryRequest, MaterialCompareRequest


def build_material_router(state) -> APIRouter:
    router = APIRouter()

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

    @router.post("/materials/compare", response_model=ApiEnvelope)
    def compare_materials(request: MaterialCompareRequest):
        return {"status": "ok", "data": state.repository.compare_materials(request.material_ids, request.weights)}

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
            state,
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

    @router.get("/regulations", response_model=ApiEnvelope)
    def list_regulations():
        return {"status": "ok", "data": state.repository.list_regulations()}

    @router.get("/regulations/{regulation_id}", response_model=ApiEnvelope)
    def get_regulation(regulation_id: str):
        regulation = state.repository.get_regulation(regulation_id)
        if not regulation:
            raise HTTPException(status_code=404, detail="Regulation not found")
        return {"status": "ok", "data": regulation}

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
            state,
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
        results = cached(state, "global_search", {"query": query}, load, ttl_seconds=state.settings.response_cache_graph_ttl_seconds)
        return {"status": "ok", "data": results}

    @router.get("/search/command", response_model=ApiEnvelope)
    def command_search(query: str, request: Request):
        current_user = state.auth.current_user(session_token(request))
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
            state,
            "command_search",
            {"query": query, "org_id": current_user["org_id"] if current_user else None},
            load,
            ttl_seconds=state.settings.response_cache_default_ttl_seconds,
        )
        return {"status": "ok", "data": payload}

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

    @router.get("/graph/relationships", response_model=ApiEnvelope)
    def graph_relationships(material_id: str | None = None):
        return {"status": "ok", "data": state.repository.relationship_preview(material_id)}

    @router.get("/graph/subgraph", response_model=ApiEnvelope)
    def graph_subgraph(material_id: str):
        data = cached(
            state,
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
            state,
            "graph_node_insight",
            {"node_id": node_id},
            lambda: state.repository.graph_node_insight(node_id),
            ttl_seconds=state.settings.response_cache_graph_ttl_seconds,
        )
        return {"status": "ok", "data": data}

    return router
