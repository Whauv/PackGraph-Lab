from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from app.api.route_helpers import (
    current_user_or_401,
    get_org_id,
    maybe_current_user,
    paginate_records,
    require_permission,
)
from app.models.schemas import (
    ApiEnvelope,
    ManualReviewCandidateRequest,
    ProvisionalReviewDecisionEnvelope,
    ProvisionalReviewDecisionRequest,
    ProvisionalReviewQueueEnvelope,
    ReviewAssignmentRequest,
    ReviewCommentRequest,
    ReviewDecisionRequest,
)


def build_review_router(state) -> APIRouter:
    router = APIRouter()

    @router.get("/review/provisional", response_model=ProvisionalReviewQueueEnvelope)
    def provisional_review_queue(request: Request, status: str | None = None, limit: int = 100):
        current_user = maybe_current_user(state, request)
        org_id = get_org_id(current_user)
        rows = [
            item
            for item in state.review_store.list(status=status, org_id=org_id, limit=limit)
            if item.get("candidate_type") == "graph_enrichment_request"
        ]
        return {"status": "ok", "data": rows}

    @router.post("/review/provisional/decision", response_model=ProvisionalReviewDecisionEnvelope)
    def provisional_review_decision(payload: ProvisionalReviewDecisionRequest, request: Request):
        current_user = maybe_current_user(state, request)
        org_id = get_org_id(current_user)
        actor_id = current_user["user_id"] if current_user else None
        status_map = {
            "promote": "approved",
            "reject": "rejected",
            "needs_more_evidence": "in_approval",
        }
        candidate = state.review_store.decide(
            payload.candidate_id,
            actor_id,
            status_map[payload.decision],
            payload.comment,
            {
                **payload.metadata,
                "provisional_decision": payload.decision,
                "neo4j_mutation_performed": False,
                "promotion_policy": "approved write-back workflow required before graph mutation",
            },
            org_id,
        )
        if not candidate:
            raise HTTPException(status_code=404, detail="Provisional review candidate not found")
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": candidate}

    @router.get("/review-candidates", response_model=ApiEnvelope)
    def review_candidates(request: Request, status: str | None = None, page: int = 1, limit: int = 24):
        current_user = current_user_or_401(state, request)
        rows = state.review_store.list(status=status, org_id=current_user["org_id"], limit=500)
        page_rows, meta = paginate_records(rows, page=page, limit=limit)
        return {"status": "ok", "data": page_rows, "meta": meta}

    @router.get("/review-candidates/summary", response_model=ApiEnvelope)
    def review_candidates_summary(request: Request):
        current_user = current_user_or_401(state, request)
        return {"status": "ok", "data": state.review_store.summary(org_id=current_user["org_id"])}

    @router.get("/review-candidates/export", response_model=ApiEnvelope)
    def export_review_candidates(output: str, request: Request, include_raw_props: bool = False):
        user = require_permission(state, request, "review:assign")
        return {
            "status": "ok",
            "data": state.review_store.export_pending(Path(output), org_id=user["org_id"], include_raw_props=include_raw_props),
        }

    @router.post("/review-candidates/import", response_model=ApiEnvelope)
    def import_review_candidates(request: Request, input_path: str, apply: bool = False):
        user = current_user_or_401(state, request)
        if apply:
            require_permission(state, request, "review:approve")
        return {"status": "ok", "data": state.review_store.import_reviewed_decisions(Path(input_path), apply=apply, org_id=user["org_id"])}

    @router.post("/review-candidates/manual", response_model=ApiEnvelope)
    def create_manual_review_candidate(payload: ManualReviewCandidateRequest, request: Request):
        actor = current_user_or_401(state, request)
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

    @router.get("/review-candidates/{candidate_id}", response_model=ApiEnvelope)
    def review_candidate_detail(candidate_id: str, request: Request):
        current_user = current_user_or_401(state, request)
        candidate = state.review_store.get(candidate_id, org_id=current_user["org_id"])
        if not candidate:
            raise HTTPException(status_code=404, detail="Review candidate not found")
        return {"status": "ok", "data": candidate}

    @router.get("/review-candidates/{candidate_id}/history", response_model=ApiEnvelope)
    def review_candidate_history(candidate_id: str, request: Request):
        user = require_permission(state, request, "review:assign")
        candidate = state.review_store.get(candidate_id, org_id=user["org_id"])
        if not candidate:
            raise HTTPException(status_code=404, detail="Review candidate not found")
        return {"status": "ok", "data": state.review_store.history(candidate_id, org_id=user["org_id"])}

    @router.post("/review-candidates/{candidate_id}/assign", response_model=ApiEnvelope)
    def assign_review_candidate(candidate_id: str, payload: ReviewAssignmentRequest, request: Request):
        actor = require_permission(state, request, "review:assign")
        candidate = state.review_store.assign(candidate_id, payload.reviewer_id, actor["user_id"], actor["org_id"])
        if not candidate:
            raise HTTPException(status_code=404, detail="Review candidate not found")
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": candidate}

    @router.post("/review-candidates/{candidate_id}/comment", response_model=ApiEnvelope)
    def comment_review_candidate(candidate_id: str, payload: ReviewCommentRequest, request: Request):
        actor = current_user_or_401(state, request)
        candidate = state.review_store.comment(candidate_id, actor["user_id"], payload.comment, actor["org_id"])
        if not candidate:
            raise HTTPException(status_code=404, detail="Review candidate not found")
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": candidate}

    @router.post("/review-candidates/{candidate_id}/decision", response_model=ApiEnvelope)
    def decide_review_candidate(candidate_id: str, payload: ReviewDecisionRequest, request: Request):
        actor = require_permission(state, request, "review:approve")
        candidate = state.review_store.decide(candidate_id, actor["user_id"], payload.status, payload.comment, payload.metadata, actor["org_id"])
        if not candidate:
            raise HTTPException(status_code=404, detail="Review candidate not found")
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": candidate}

    return router
