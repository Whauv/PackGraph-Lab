from __future__ import annotations

from fastapi import HTTPException, Request

from app.core.config import DEFAULT_ORG_ID


def session_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return request.headers.get("X-Session-Token")


def get_org_id(user) -> str:
    return user["org_id"] if user else DEFAULT_ORG_ID


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


def current_user_or_401(state, request: Request):
    user = state.auth.current_user(session_token(request))
    if not user:
        raise HTTPException(status_code=401, detail="No active user session")
    return user


def maybe_current_user(state, request: Request):
    return state.auth.current_user(session_token(request))


def require_permission(state, request: Request, permission: str):
    user = current_user_or_401(state, request)
    if not state.auth.has_permission(user, permission):
        raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
    return user


def maybe_idempotent(state, request: Request, payload: dict, action):
    idem_key = request.headers.get("Idempotency-Key")
    if not idem_key:
        return action()
    user = maybe_current_user(state, request)
    org_id = get_org_id(user)
    request_hash = state.idempotency.request_hash(request, str(payload).encode("utf-8"))
    existing = state.idempotency.get(idem_key, org_id=org_id)
    if existing:
        if existing["request_hash"] != request_hash:
            raise HTTPException(status_code=409, detail="Idempotency key reuse with a different payload.")
        return state.idempotency.load_response(existing)
    response_payload = action()
    state.idempotency.store(idem_key, request.method, request.url.path, request_hash, response_payload, org_id=org_id)
    return response_payload


def cached(state, namespace: str, payload: dict, loader, ttl_seconds: int | None = None):
    return state.cache.get_or_set(
        f"route:{namespace}",
        payload,
        ttl_seconds=ttl_seconds or state.settings.response_cache_default_ttl_seconds,
        loader=loader,
    )
