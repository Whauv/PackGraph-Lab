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
from app.repositories.graph_repository import GraphConnectionError, GraphQueryFailure, build_graph_repository
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
from app.services.operations_service import OperationsService
from app.services.private_data_service import PrivateDataService
from app.services.query_engine import QueryEngine
from app.services.response_cache_service import ResponseCacheService
from app.services.runtime_maintenance_service import RuntimeMaintenanceService
from app.services.scenario_history_service import ScenarioHistoryService
from app.services.source_intake_service import SourceIntakeService
from scripts.evaluate_entity_resolution import main as evaluate_entity_resolution_main
from scripts.ingest_graph import main as ingest_main


class AppState:
    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.requested_graph_backend = settings.graph_backend
        self.runtime_db = build_runtime_db(settings)
        self.observability = ObservabilityService(settings)
        self.cache = ResponseCacheService()
        self.rate_limiter = RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)
        self.idempotency = IdempotencyService(self.runtime_db)
        self.repository = build_graph_repository(settings)
        self.runtime_maintenance = RuntimeMaintenanceService(settings)
        self.private_data = PrivateDataService(
            settings.private_data_dir,
            settings.sqlite_ingest_path,
            parser_name=settings.ingest_parser_name,
            parser_version=settings.ingest_parser_version,
            schema_version=settings.ingest_schema_version,
            transform_cache_path=settings.transform_cache_path,
        )
        self.source_intake = SourceIntakeService(settings.packgraph_runtime_dir)
        self.query_engine = QueryEngine(self.repository, self.private_data, self.source_intake)
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
        self.repository_status = self._repository_status()
        self.operations = OperationsService(self)
        self.observability.set_gauge("graph_backend_active", self.repository_status["active_backend"])
        self.observability.set_gauge("graph_backend_requested", self.repository_status["requested_backend"])

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
        self.observability.record_job("running")
        argv: list[str] = []
        if payload.get("json_source_dir"):
            argv.extend(["--json-source-dir", payload["json_source_dir"]])
        if payload.get("sqlite_path"):
            argv.extend(["--sqlite-path", payload["sqlite_path"]])
        if payload.get("profile_only"):
            argv.append("--profile-only")
        if payload.get("skip_generated"):
            argv.append("--skip-generated")
        result = ingest_main(argv)
        self.cache.invalidate_prefix("route:")
        self.observability.record_job("completed")
        return result

    def _job_evaluate_entity_resolution(self, payload: dict) -> dict:
        self.observability.record_job("running")
        argv: list[str] = []
        if payload.get("dataset"):
            argv.extend(["--dataset", payload["dataset"]])
        result = evaluate_entity_resolution_main(argv)
        self.observability.record_job("completed")
        return result

    def _job_import_review_decisions(self, payload: dict) -> dict:
        source = Path(payload["input"])
        self.observability.record_job("running")
        result = self.review_store.import_reviewed_decisions(source, apply=bool(payload.get("apply")))
        self.cache.invalidate_prefix("route:")
        self.observability.record_job("completed")
        return result

    def _job_document_parse(self, payload: dict) -> dict:
        self.observability.record_job("running")
        return {
            "status": "accepted",
            "message": "Document parse jobs should be created during upload flows with artifact context.",
            "payload": payload,
        }

    def _job_export_bundle(self, payload: dict) -> dict:
        self.observability.record_job("running")
        kind = payload.get("kind", "executive_summary")
        return {"status": "accepted", "kind": kind, "payload": payload}

    def _repository_status(self) -> dict:
        return {
            "requested_backend": "neo4j",
            "active_backend": "neo4j",
            "degraded": False,
            "fallback_reason": None,
            "graph": self.repository.graph_health(),
        }


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


def _error_payload(code: str, detail: str, *, errors: list[dict] | None = None) -> dict:
    return {
        "status": "error",
        "error": code,
        "detail": detail,
        "errors": errors or [],
    }


@app.middleware("http")
async def request_controls(request: Request, call_next):
    started = time.perf_counter()
    client = request.client.host if request.client else "unknown"
    limiter_key = f"{client}:{request.url.path}"
    if not state.rate_limiter.check(limiter_key, time.time()):
        state.observability.log_event("rate_limited", {"path": request.url.path, "client": client})
        return JSONResponse(status_code=429, content=_error_payload("rate_limited", "Too many requests. Retry later."))
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    state.observability.record_request(request.url.path, response.status_code, elapsed_ms)
    return response


@app.exception_handler(Exception)
async def generic_exception_handler(_: Request, exc: Exception):
    state.observability.log_event("unhandled_exception", {"error": str(exc)})
    return JSONResponse(
        status_code=500,
        content=_error_payload("internal_error", "An unexpected server error occurred."),
    )


@app.exception_handler(GraphConnectionError)
async def graph_connection_exception_handler(_: Request, exc: GraphConnectionError):
    state.observability.log_event("graph_connection_error", {"detail": str(exc)})
    return JSONResponse(
        status_code=503,
        content=_error_payload("graph_connection_unavailable", str(exc)),
    )


@app.exception_handler(GraphQueryFailure)
async def graph_query_exception_handler(_: Request, exc: GraphQueryFailure):
    state.observability.log_event("graph_query_failure", {"detail": str(exc)})
    return JSONResponse(
        status_code=500,
        content=_error_payload("graph_query_failed", str(exc)),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
    state.observability.log_event("http_exception", {"status_code": exc.status_code, "detail": detail})
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(f"http_{exc.status_code}", detail),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    errors = exc.errors()
    state.observability.log_event("validation_error", {"errors": errors})
    return JSONResponse(
        status_code=422,
        content=_error_payload("validation_error", "Request validation failed.", errors=errors),
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
            "backend": "neo4j",
            "runtime_profile": state.settings.runtime_profile,
            "repository_status": state.repository_status,
            "private_data_active": state.private_data.has_data(),
            "runtime_db": state.runtime_db.health(),
            "job_summary": state.jobs.summary(),
            "cache": state.cache.stats(),
            "runtime_maintenance": state.runtime_maintenance.summary(),
        },
    }


@app.get("/health/live")
def health_live():
    return {"status": "ok", "data": {"live": True, "date": "2026-08-21", "runtime_profile": state.settings.runtime_profile}}


@app.get("/health/ready")
def health_ready():
    ready = state.repository.graph_health()["connected"] or state.settings.neo4j_test_stub
    warnings: list[str] = [] if ready else ["Neo4j is configured but not connected."]
    return {
        "status": "ok",
        "data": {
            "ready": ready,
            "warnings": warnings,
            "graph_backend": "neo4j",
            "repository_status": state.repository_status,
            "runtime_db": state.runtime_db.health(),
        },
    }


@app.get("/metrics")
def metrics():
    return {"status": "ok", "data": state.observability.metrics()}
