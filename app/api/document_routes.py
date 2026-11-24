from __future__ import annotations

from datetime import datetime, UTC

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.api.route_helpers import cached, get_org_id, maybe_current_user, paginate_records, session_token
from app.models.schemas import ApiEnvelope


def build_document_router(state) -> APIRouter:
    router = APIRouter()

    @router.get("/documents/search", response_model=ApiEnvelope)
    def documents_search(query: str, material_id: str | None = None, page: int = 1, limit: int = 20):
        rows = cached(
            state,
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
        current_user = state.auth.current_user(session_token(request))
        org_id = get_org_id(current_user)
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

    @router.get("/source-intake/sources", response_model=ApiEnvelope)
    def source_intake_sources(request: Request, limit: int = 25):
        current_user = maybe_current_user(state, request)
        org_id = get_org_id(current_user)
        return {"status": "ok", "data": state.source_intake.list_sources(limit=limit, org_id=org_id)}

    @router.get("/source-intake/search", response_model=ApiEnvelope)
    def source_intake_search(request: Request, query: str, limit: int = 8):
        current_user = maybe_current_user(state, request)
        org_id = get_org_id(current_user)
        return {"status": "ok", "data": state.source_intake.search(query, limit=limit, org_id=org_id)}

    @router.post("/source-intake/upload", response_model=ApiEnvelope)
    async def source_intake_upload(
        request: Request,
        file: UploadFile = File(...),
        source_type: str | None = Form(None),
        title: str | None = Form(None),
    ):
        content = await file.read()
        current_user = maybe_current_user(state, request)
        org_id = get_org_id(current_user)
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

    return router
