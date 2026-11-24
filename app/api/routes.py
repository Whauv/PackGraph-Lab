from __future__ import annotations

from fastapi import APIRouter

from app.api.auth_routes import build_auth_router
from app.api.community_routes import build_community_router
from app.api.document_routes import build_document_router
from app.api.material_routes import build_material_router
from app.api.ops_routes import build_ops_router
from app.api.query_routes import build_query_router
from app.api.review_routes import build_review_router


def build_router(state) -> APIRouter:
    router = APIRouter()
    router.include_router(build_auth_router(state))
    router.include_router(build_material_router(state))
    router.include_router(build_query_router(state))
    router.include_router(build_review_router(state))
    router.include_router(build_document_router(state))
    router.include_router(build_community_router(state))
    router.include_router(build_ops_router(state))
    return router
