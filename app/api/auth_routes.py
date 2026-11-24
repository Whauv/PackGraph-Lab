from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.route_helpers import (
    cached,
    current_user_or_401,
    maybe_idempotent,
    require_permission,
    session_token,
)
from app.models.schemas import ApiEnvelope, LoginRequest, RegisterRequest, WorkspaceSaveRequest


def build_auth_router(state) -> APIRouter:
    router = APIRouter()

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
        return maybe_idempotent(state, request, payload.model_dump(), create)

    @router.post("/auth/logout", response_model=ApiEnvelope)
    def auth_logout(request: Request):
        state.auth.logout(session_token(request))
        return {"status": "ok", "data": {"logged_out": True}}

    @router.get("/auth/session", response_model=ApiEnvelope)
    def auth_session(request: Request):
        return {"status": "ok", "data": state.auth.current_user(session_token(request))}

    @router.get("/auth/roles", response_model=ApiEnvelope)
    def auth_roles():
        return {"status": "ok", "data": state.auth.list_roles()}

    @router.get("/auth/organizations", response_model=ApiEnvelope)
    def auth_organizations():
        return {"status": "ok", "data": state.auth.list_organizations()}

    @router.get("/workspaces", response_model=ApiEnvelope)
    def list_workspaces(request: Request):
        user = state.auth.current_user(session_token(request))
        return {"status": "ok", "data": state.auth.list_workspaces(user["user_id"] if user else None)}

    @router.post("/workspaces", response_model=ApiEnvelope)
    def save_workspace(payload: WorkspaceSaveRequest, request: Request):
        user = require_permission(state, request, "workspaces:write")
        response = maybe_idempotent(
            state,
            request,
            payload.model_dump(),
            lambda: {"status": "ok", "data": state.auth.save_workspace(user["user_id"], payload.model_dump())},
        )
        state.cache.invalidate_prefix("route:notifications")
        return response

    @router.get("/searches", response_model=ApiEnvelope)
    def list_saved_searches(request: Request):
        user = current_user_or_401(state, request)
        return {"status": "ok", "data": state.auth.list_saved_searches(user["user_id"])}

    @router.post("/searches", response_model=ApiEnvelope)
    def save_search(payload: dict, request: Request):
        user = require_permission(state, request, "search:save")
        response = maybe_idempotent(
            state,
            request,
            payload,
            lambda: {"status": "ok", "data": state.auth.save_search(user["user_id"], payload)},
        )
        state.cache.invalidate_prefix("route:notifications")
        return response

    return router
