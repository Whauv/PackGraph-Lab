from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os

from app.core.runtime_paths import RuntimePaths
from app.services.security_utils import secure_mkdir, secure_write_text

DEFAULT_ORG_ID = "ORG-001"


def _env(name: str) -> str | None:
    return os.getenv(name) or None


def _env_bool(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    project_name: str = "PackGraph Lab"
    runtime_profile: str = "local-demo"
    graph_backend: str = "neo4j"
    packgraph_data_dir: Path = Path("./data/generated")
    packgraph_runtime_dir: Path = Path("./data/runtime")
    packgraph_staging_dir: Path = Path("./data/staging")
    private_data_dir: Path = Path("./private_data")
    json_ingest_dir: Path = Path("./private_data")
    sqlite_ingest_path: Path | None = None
    runtime_db_path: Path = Path("./data/runtime/packgraph_runtime.db")
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "packgraph-dev-default"
    neo4j_database: str = "neo4j"
    neo4j_auto_ingest: bool = False
    neo4j_test_stub: bool = False
    ingest_parser_name: str = "packgraph-local-ingest"
    ingest_parser_version: str = "2.0"
    ingest_schema_version: str = "2026.08.02"
    ingest_report_dir: Path = Path("./data/runtime/reports")
    ingest_state_dir: Path = Path("./data/runtime/ingest_state")
    transform_cache_path: Path = Path("./data/runtime/transform_cache.json")
    graph_schema_version: str = "2026.08.02"
    er_eval_dataset_path: Path = Path("./tests/fixtures/entity_resolution_eval.json")
    llm_enabled: bool = False
    llm_backend: str = "disabled"
    embeddings_backend: str = "local"
    er_backend: str = "heuristic"
    adjudicator_backend: str = "local"
    outbound_field_allowlist: str = "entity_type,label,score,preview,fields,question,intent,route,top_rows,missing_evidence,entity_resolution"
    project_memory_path: Path = Path("./data/staging/project_memory.json")
    review_candidates_path: Path = Path("./data/staging/agent_review_candidates.json")
    agent_audit_path: Path = Path("./data/runtime/agent_audit.jsonl")
    review_audit_path: Path = Path("./data/runtime/review_audit.jsonl")
    entity_resolution_audit_path: Path = Path("./data/runtime/entity_resolution_audit.jsonl")
    match_decision_cache_path: Path = Path("./data/runtime/match_decision_cache.json")
    er_review_threshold: float = 0.68
    er_auto_accept_threshold: float = 0.9
    auth_secret: str = "packgraph-dev-secret"
    session_ttl_hours: int = 12
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    observability_log_path: Path = Path("./data/runtime/app_events.jsonl")
    metrics_path: Path = Path("./data/runtime/metrics_snapshot.json")
    response_cache_default_ttl_seconds: int = 45
    response_cache_graph_ttl_seconds: int = 30
    response_cache_analytics_ttl_seconds: int = 60
    request_timeout_ms: int = 8000
    request_retry_attempts: int = 2
    cleanup_retention_days: int = 7
    cleanup_max_report_files: int = 30
    cleanup_max_runtime_logs: int = 12
    neo4j_ready_timeout_seconds: int = 2


def _settings_from_env() -> Settings:
    """Build Settings by reading env vars; unset vars fall through to dataclass defaults."""
    overrides: dict = {}

    if v := _env("PACKGRAPH_RUNTIME_PROFILE"):
        overrides["runtime_profile"] = v
    if v := _env("PACKGRAPH_DATA_DIR"):
        overrides["packgraph_data_dir"] = Path(v)
    if v := _env("PACKGRAPH_RUNTIME_DIR"):
        overrides["packgraph_runtime_dir"] = Path(v)
    if v := _env("PACKGRAPH_STAGING_DIR"):
        overrides["packgraph_staging_dir"] = Path(v)
    if v := _env("PACKGRAPH_PRIVATE_DATA_DIR"):
        overrides["private_data_dir"] = Path(v)
    if v := _env("PACKGRAPH_JSON_INGEST_DIR"):
        overrides["json_ingest_dir"] = Path(v)
    if v := _env("PACKGRAPH_SQLITE_INGEST_PATH"):
        overrides["sqlite_ingest_path"] = Path(v)
    if v := _env("PACKGRAPH_RUNTIME_DB_PATH"):
        overrides["runtime_db_path"] = Path(v)
    if v := _env("NEO4J_URI"):
        overrides["neo4j_uri"] = v
    if v := (_env("NEO4J_USER") or _env("NEO4J_USERNAME")):
        overrides["neo4j_user"] = v
    if v := _env("NEO4J_PASSWORD"):
        overrides["neo4j_password"] = v
    if v := _env("NEO4J_DATABASE"):
        overrides["neo4j_database"] = v
    if (v := _env_bool("NEO4J_AUTO_INGEST")) is not None:
        overrides["neo4j_auto_ingest"] = v
    if (v := _env_bool("PACKGRAPH_NEO4J_TEST_STUB")) is not None:
        overrides["neo4j_test_stub"] = v
    if v := _env("PACKGRAPH_INGEST_PARSER_NAME"):
        overrides["ingest_parser_name"] = v
    if v := _env("PACKGRAPH_INGEST_PARSER_VERSION"):
        overrides["ingest_parser_version"] = v
    if v := _env("PACKGRAPH_INGEST_SCHEMA_VERSION"):
        overrides["ingest_schema_version"] = v
    if v := _env("PACKGRAPH_INGEST_REPORT_DIR"):
        overrides["ingest_report_dir"] = Path(v)
    if v := _env("PACKGRAPH_INGEST_STATE_DIR"):
        overrides["ingest_state_dir"] = Path(v)
    if v := _env("PACKGRAPH_TRANSFORM_CACHE_PATH"):
        overrides["transform_cache_path"] = Path(v)
    if v := _env("PACKGRAPH_GRAPH_SCHEMA_VERSION"):
        overrides["graph_schema_version"] = v
    if v := _env("PACKGRAPH_ER_EVAL_DATASET_PATH"):
        overrides["er_eval_dataset_path"] = Path(v)
    if (v := _env_bool("PACKGRAPH_LLM_ENABLED")) is not None:
        overrides["llm_enabled"] = v
    if v := _env("PACKGRAPH_LLM_BACKEND"):
        overrides["llm_backend"] = v
    if v := _env("PACKGRAPH_EMBEDDINGS_BACKEND"):
        overrides["embeddings_backend"] = v
    if v := _env("PACKGRAPH_ER_BACKEND"):
        overrides["er_backend"] = v
    if v := _env("PACKGRAPH_ADJUDICATOR_BACKEND"):
        overrides["adjudicator_backend"] = v
    if v := _env("PACKGRAPH_OUTBOUND_FIELD_ALLOWLIST"):
        overrides["outbound_field_allowlist"] = v
    if v := _env("PACKGRAPH_PROJECT_MEMORY_PATH"):
        overrides["project_memory_path"] = Path(v)
    if v := _env("PACKGRAPH_REVIEW_CANDIDATES_PATH"):
        overrides["review_candidates_path"] = Path(v)
    if v := _env("PACKGRAPH_AGENT_AUDIT_PATH"):
        overrides["agent_audit_path"] = Path(v)
    if v := _env("PACKGRAPH_REVIEW_AUDIT_PATH"):
        overrides["review_audit_path"] = Path(v)
    if v := _env("PACKGRAPH_ENTITY_RESOLUTION_AUDIT_PATH"):
        overrides["entity_resolution_audit_path"] = Path(v)
    if v := _env("PACKGRAPH_MATCH_DECISION_CACHE_PATH"):
        overrides["match_decision_cache_path"] = Path(v)
    if v := _env("PACKGRAPH_ER_REVIEW_THRESHOLD"):
        overrides["er_review_threshold"] = float(v)
    if v := _env("PACKGRAPH_ER_AUTO_ACCEPT_THRESHOLD"):
        overrides["er_auto_accept_threshold"] = float(v)
    if v := _env("PACKGRAPH_AUTH_SECRET"):
        overrides["auth_secret"] = v
    if v := _env("PACKGRAPH_SESSION_TTL_HOURS"):
        overrides["session_ttl_hours"] = int(v)
    if v := _env("PACKGRAPH_RATE_LIMIT_REQUESTS"):
        overrides["rate_limit_requests"] = int(v)
    if v := _env("PACKGRAPH_RATE_LIMIT_WINDOW_SECONDS"):
        overrides["rate_limit_window_seconds"] = int(v)
    if v := _env("PACKGRAPH_OBSERVABILITY_LOG_PATH"):
        overrides["observability_log_path"] = Path(v)
    if v := _env("PACKGRAPH_METRICS_PATH"):
        overrides["metrics_path"] = Path(v)
    if v := _env("PACKGRAPH_CACHE_TTL_SECONDS"):
        overrides["response_cache_default_ttl_seconds"] = int(v)
    if v := _env("PACKGRAPH_GRAPH_CACHE_TTL_SECONDS"):
        overrides["response_cache_graph_ttl_seconds"] = int(v)
    if v := _env("PACKGRAPH_ANALYTICS_CACHE_TTL_SECONDS"):
        overrides["response_cache_analytics_ttl_seconds"] = int(v)
    if v := _env("PACKGRAPH_REQUEST_TIMEOUT_MS"):
        overrides["request_timeout_ms"] = int(v)
    if v := _env("PACKGRAPH_REQUEST_RETRY_ATTEMPTS"):
        overrides["request_retry_attempts"] = int(v)
    if v := _env("PACKGRAPH_CLEANUP_RETENTION_DAYS"):
        overrides["cleanup_retention_days"] = int(v)
    if v := _env("PACKGRAPH_CLEANUP_MAX_REPORT_FILES"):
        overrides["cleanup_max_report_files"] = int(v)
    if v := _env("PACKGRAPH_CLEANUP_MAX_RUNTIME_LOGS"):
        overrides["cleanup_max_runtime_logs"] = int(v)
    if v := _env("PACKGRAPH_NEO4J_READY_TIMEOUT_SECONDS"):
        overrides["neo4j_ready_timeout_seconds"] = int(v)

    return Settings(**overrides)


def ensure_runtime_files(settings: Settings) -> None:
    """Create directories and seed files required at startup. Called once from main."""
    RuntimePaths.from_settings(settings).ensure_directories()
    secure_mkdir(settings.private_data_dir)
    secure_mkdir(settings.json_ingest_dir)
    secure_mkdir(settings.observability_log_path.parent)
    secure_mkdir(settings.metrics_path.parent)
    secure_mkdir(settings.transform_cache_path.parent)
    if not settings.project_memory_path.exists():
        secure_write_text(
            settings.project_memory_path,
            '{"saved_entities":[],"saved_suppliers":[],"prior_questions":[],"compared_entities":[],"user_assumptions":[],"uploaded_file_references":[],"investigation_notes":[]}',
        )
    if not settings.review_candidates_path.exists():
        secure_write_text(settings.review_candidates_path, "[]")
    if not settings.match_decision_cache_path.exists():
        secure_write_text(settings.match_decision_cache_path, "{}")
    if not settings.transform_cache_path.exists():
        secure_write_text(settings.transform_cache_path, "{}")


@lru_cache
def get_settings() -> Settings:
    settings = _settings_from_env()
    ensure_runtime_files(settings)
    return settings
