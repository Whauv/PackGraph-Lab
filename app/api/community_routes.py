from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.route_helpers import (
    cached,
    current_user_or_401,
    get_org_id,
    maybe_current_user,
    maybe_idempotent,
    paginate_records,
    require_permission,
)
from app.models.schemas import (
    ApiEnvelope,
    CommunityPostCreate,
    CommunityReplyCreate,
    ContributionCreate,
    ContributionReviewRequest,
)


def build_community_router(state) -> APIRouter:
    router = APIRouter()

    @router.get("/contributions/roles", response_model=ApiEnvelope)
    def contribution_roles():
        return {"status": "ok", "data": state.contributions.list_roles()}

    @router.get("/contributions", response_model=ApiEnvelope)
    def list_contributions(request: Request):
        current_user = maybe_current_user(state, request)
        org_id = get_org_id(current_user)
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
        current_user = require_permission(state, request, "contributions:write")
        if payload.related_entity_type or payload.related_entity_id:
            validation = state.repository.validate_entity_reference(payload.related_entity_type, payload.related_entity_id)
            if not validation["valid"]:
                raise HTTPException(status_code=400, detail=validation["message"])
        submitted_by = current_user["name"]
        response = maybe_idempotent(
            state,
            request,
            payload.model_dump(),
            lambda: {"status": "ok", "data": state.contributions.create(payload.model_dump(), submitted_by, org_id=current_user["org_id"])},
        )
        state.cache.invalidate_prefix("route:notifications")
        return response

    @router.post("/contributions/{contribution_id}/review", response_model=ApiEnvelope)
    def review_contribution(contribution_id: str, payload: ContributionReviewRequest, request: Request):
        reviewer = require_permission(state, request, "contributions:review")
        record = state.contributions.review(contribution_id, payload.status, reviewer["name"], payload.reviewer_note, org_id=reviewer["org_id"])
        if not record:
            raise HTTPException(status_code=404, detail="Contribution not found")
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": record}

    @router.get("/community/channels", response_model=ApiEnvelope)
    def community_channels(request: Request):
        current_user = maybe_current_user(state, request)
        return {"status": "ok", "data": state.community.list_channels(org_id=get_org_id(current_user))}

    @router.get("/community/posts", response_model=ApiEnvelope)
    def community_posts(
        request: Request,
        channel_id: str | None = None,
        moderation_state: str | None = None,
        related_entity_id: str | None = None,
        page: int = 1,
        limit: int = 12,
    ):
        current_user = maybe_current_user(state, request)
        org_id = get_org_id(current_user)
        rows = cached(
            state,
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
        current_user = maybe_current_user(state, request)
        post = state.community.get_post(post_id, get_org_id(current_user))
        if not post:
            raise HTTPException(status_code=404, detail="Community post not found")
        return {"status": "ok", "data": post}

    @router.post("/community/posts", response_model=ApiEnvelope)
    def create_community_post(payload: CommunityPostCreate, request: Request):
        current_user = require_permission(state, request, "community:write")
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
        current_user = current_user_or_401(state, request)
        post = state.community.upvote(post_id, current_user["org_id"])
        if not post:
            raise HTTPException(status_code=404, detail="Community post not found")
        state.cache.invalidate_prefix("route:community_posts")
        return {"status": "ok", "data": post}

    @router.post("/community/posts/{post_id}/save", response_model=ApiEnvelope)
    def save_community_post(post_id: str, request: Request):
        current_user = current_user_or_401(state, request)
        post = state.community.save_post(post_id, current_user["org_id"])
        if not post:
            raise HTTPException(status_code=404, detail="Community post not found")
        state.cache.invalidate_prefix("route:community_posts")
        return {"status": "ok", "data": post}

    @router.post("/community/posts/{post_id}/reply", response_model=ApiEnvelope)
    def reply_community_post(post_id: str, payload: CommunityReplyCreate, request: Request):
        current_user = require_permission(state, request, "community:write")
        post = state.community.add_reply(post_id, payload.body, current_user["name"], current_user["role_title"], current_user["org_id"])
        if not post:
            raise HTTPException(status_code=404, detail="Community post not found")
        state.cache.invalidate_prefix("route:community_posts")
        return {"status": "ok", "data": post}

    @router.post("/community/posts/{post_id}/pin", response_model=ApiEnvelope)
    def pin_community_post(post_id: str, request: Request):
        current_user = require_permission(state, request, "community:pin")
        post = state.community.pin(post_id, current_user["org_id"])
        if not post:
            raise HTTPException(status_code=404, detail="Community post not found")
        state.cache.invalidate_prefix("route:community_posts")
        state.cache.invalidate_prefix("route:notifications")
        return {"status": "ok", "data": post}

    return router
