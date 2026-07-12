from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import build_router
from app.core.config import get_settings
from app.repositories.graph_repository import LocalGraphRepository
from app.services.auth_service import AuthService
from app.services.export_service import ExportService
from app.services.investigation_service import InvestigationService
from app.services.query_engine import QueryEngine


class AppState:
    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.repository = LocalGraphRepository()
        self.query_engine = QueryEngine(self.repository)
        self.auth = AuthService(settings.packgraph_runtime_dir)
        self.auth.ensure_seed()
        self.investigations = InvestigationService(settings.packgraph_runtime_dir)
        self.investigations.ensure_seed(self.repository.bundle["investigations"])
        self.exports = ExportService()

    def benchmarks(self) -> dict:
        benchmark_path = Path("data/runtime/benchmark_results.json")
        if benchmark_path.exists():
            with benchmark_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        return {
            "status": "not-run",
            "notes": "Run python scripts/benchmark_backends.py after starting Neo4j and optionally Memgraph.",
        }


state = AppState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="PackGraph Lab API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def generic_exception_handler(_: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"status": "error", "error": "internal_error", "detail": str(exc)})


app.include_router(build_router(state))
app.mount("/assets", StaticFiles(directory="web/assets"), name="assets")


@app.get("/")
def home():
    return FileResponse("web/index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse("web/assets/favicon.svg", media_type="image/svg+xml")


@app.get("/health")
def health():
    return {"status": "ok", "data": {"service": "PackGraph Lab", "backend": state.settings.graph_backend}}
