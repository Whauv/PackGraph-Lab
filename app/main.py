from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import build_router
from app.core.config import get_settings
from app.core.request_controls import IdempotencyService, RateLimiter
from app.core.runtime_db import build_runtime_db
from app.repositories.graph_repository import build_graph_repository
from app.services.auth_service import AuthService
from app.services.agent_review import ReviewCandidateStore
from app.services.community_service import CommunityService
from app.services.component_discovery_service import ComponentDiscoveryService
from app.services.contribution_service import ContributionService
from app.services.document_intelligence_service import DocumentIntelligenceService
from app.services.export_service import ExportService
from app.services.governance_service import GovernanceService
from app.services.investigation_service import InvestigationService
from app.services.job_service import JobService
from app.services.lineage_service import LineageService
from app.services.observability_service import ObservabilityService
from app.services.private_data_service import PrivateDataService
from app.services.query_engine import QueryEngine
from app.services.scenario_history_service import ScenarioHistoryService
from scripts.evaluate_entity_resolution import main as evaluate_entity_resolution_main
from scripts.ingest_graph import main as ingest_main


class AppState:
    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.runtime_db = build_runtime_db(settings)
        self.observability = ObservabilityService(settings)
        self.rate_limiter = RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)
        self.idempotency = IdempotencyService(self.runtime_db)
        self.repository = build_graph_repository(settings)
        self.private_data = PrivateDataService(
            settings.private_data_dir,
            settings.sqlite_ingest_path,
            parser_name=settings.ingest_parser_name,
            parser_version=settings.ingest_parser_version,
            schema_version=settings.ingest_schema_version,
            transform_cache_path=settings.transform_cache_path,
        )
        self.query_engine = QueryEngine(self.repository, self.private_data)
        self.auth = AuthService(settings, self.runtime_db)
        self.auth.ensure_seed()
        self.review_store = ReviewCandidateStore(settings, self.runtime_db)
        self.governance = GovernanceService(settings, self.runtime_db)
        self.governance.ensure_seed()
        self.lineage = LineageService(settings, self.runtime_db, self.governance)
        self.documents = DocumentIntelligenceService(settings.packgraph_runtime_dir, self.repository)
        self.documents.ensure_seed()
        self.components = ComponentDiscoveryService(settings.packgraph_runtime_dir, self.repository)
        self.components.ensure_seed()
        self.contributions = ContributionService(settings.packgraph_runtime_dir)
        self.contributions.ensure_seed()
        self.community = CommunityService(settings.packgraph_runtime_dir)
        self.community.ensure_seed()
        self.investigations = InvestigationService(settings.packgraph_runtime_dir)
        self.investigations.ensure_seed(self.repository.bundle["investigations"])
        self.scenario_history = ScenarioHistoryService(settings.packgraph_runtime_dir)
        self.exports = ExportService()
        self.jobs = JobService(settings, self.runtime_db)
        self.jobs.register_handler("ingest", self._job_ingest)
        self.jobs.register_handler("evaluate_entity_resolution", self._job_evaluate_entity_resolution)
        self.jobs.register_handler("import_review_decisions", self._job_import_review_decisions)
        self.jobs.register_handler("document_parse", self._job_document_parse)
        self.jobs.register_handler("export_bundle", self._job_export_bundle)

    def benchmarks(self) -> dict:
        benchmark_path = Path("data/runtime/benchmark_results.json")
        if benchmark_path.exists():
            with benchmark_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        return {
            "status": "not-run",
            "notes": "Run python scripts/benchmark_backends.py after starting Neo4j.",
        }

    def _job_ingest(self, payload: dict) -> dict:
        argv: list[str] = []
        if payload.get("json_source_dir"):
            argv.extend(["--json-source-dir", payload["json_source_dir"]])
        if payload.get("sqlite_path"):
            argv.extend(["--sqlite-path", payload["sqlite_path"]])
        if payload.get("profile_only"):
            argv.append("--profile-only")
        if payload.get("skip_generated"):
            argv.append("--skip-generated")
        return ingest_main(argv)

    def _job_evaluate_entity_resolution(self, payload: dict) -> dict:
        argv: list[str] = []
        if payload.get("dataset"):
            argv.extend(["--dataset", payload["dataset"]])
        return evaluate_entity_resolution_main(argv)

    def _job_import_review_decisions(self, payload: dict) -> dict:
        source = Path(payload["input"])
        return self.review_store.import_reviewed_decisions(source, apply=bool(payload.get("apply")))

    def _job_document_parse(self, payload: dict) -> dict:
        return {
            "status": "accepted",
            "message": "Document parse jobs should be created during upload flows with artifact context.",
            "payload": payload,
        }

    def _job_export_bundle(self, payload: dict) -> dict:
        kind = payload.get("kind", "executive_summary")
        return {"status": "accepted", "kind": kind, "payload": payload}


state = AppState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        close = getattr(state.repository, "close", None)
        if callable(close):
            close()


app = FastAPI(title="PackGraph Lab API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_controls(request: Request, call_next):
    started = time.perf_counter()
    client = request.client.host if request.client else "unknown"
    limiter_key = f"{client}:{request.url.path}"
    if not state.rate_limiter.check(limiter_key, time.time()):
        state.observability.log_event("rate_limited", {"path": request.url.path, "client": client})
        return JSONResponse(status_code=429, content={"status": "error", "error": "rate_limited", "detail": "Too many requests. Retry later."})
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    state.observability.record_request(request.url.path, response.status_code, elapsed_ms)
    return response


@app.exception_handler(Exception)
async def generic_exception_handler(_: Request, exc: Exception):
    state.observability.log_event("unhandled_exception", {"error": str(exc)})
    return JSONResponse(status_code=500, content={"status": "error", "error": "internal_error", "detail": str(exc)})


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
    state.observability.log_event("http_exception", {"status_code": exc.status_code, "detail": detail})
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "error": f"http_{exc.status_code}", "detail": detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    state.observability.log_event("validation_error", {"errors": exc.errors()})
    return JSONResponse(
        status_code=422,
        content={"status": "error", "error": "validation_error", "detail": json.dumps(exc.errors())},
    )


app.include_router(build_router(state))
app.mount("/assets", StaticFiles(directory="web/assets"), name="assets")


@app.get("/")
def home():
    return FileResponse("web/landing.html")


@app.get("/product")
def product():
    return FileResponse("web/index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse("web/assets/favicon.svg", media_type="image/svg+xml")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "data": {
            "service": "PackGraph Lab",
            "backend": state.settings.graph_backend,
            "private_data_active": state.private_data.has_data(),
            "runtime_db": state.runtime_db.health(),
            "job_summary": state.jobs.summary(),
        },
    }


@app.get("/health/live")
def health_live():
    return {"status": "ok", "data": {"live": True, "date": "2026-07-31"}}


@app.get("/health/ready")
def health_ready():
    return {
        "status": "ok",
        "data": {
            "ready": True,
            "graph_backend": state.settings.graph_backend,
            "runtime_db": state.runtime_db.health(),
        },
    }


@app.get("/metrics")
def metrics():
    return {"status": "ok", "data": state.observability.metrics()}
