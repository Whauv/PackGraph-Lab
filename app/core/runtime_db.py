from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, UTC
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from app.core.config import Settings


MIGRATIONS: list[tuple[str, list[str]]] = [
    (
        "001_runtime_core",
        [
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS organizations (
                org_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role_id TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY(org_id) REFERENCES organizations(org_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                last_seen_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                workspace_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                filters_json TEXT NOT NULL,
                selected_material_ids_json TEXT NOT NULL,
                active_tab TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS saved_searches (
                saved_search_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                saved_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS review_candidates (
                candidate_id TEXT PRIMARY KEY,
                candidate_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL,
                review_before_writeback INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                assigned_reviewer_id TEXT,
                decision_state TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS review_history (
                history_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                actor_id TEXT,
                action TEXT NOT NULL,
                comment TEXT,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(candidate_id) REFERENCES review_candidates(candidate_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                owner_id TEXT,
                payload_json TEXT NOT NULL,
                result_json TEXT,
                error_code TEXT,
                error_detail TEXT,
                idempotency_key TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                run_after TEXT NOT NULL,
                dead_lettered_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_idempotency
            ON jobs(idempotency_key)
            WHERE idempotency_key IS NOT NULL
            """,
            """
            CREATE TABLE IF NOT EXISTS idempotency_records (
                idem_key TEXT PRIMARY KEY,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
        ],
    ),
    (
        "002_multi_tenant_governance",
        [
            "ALTER TABLE sessions ADD COLUMN org_id TEXT",
            "ALTER TABLE workspaces ADD COLUMN org_id TEXT",
            "ALTER TABLE saved_searches ADD COLUMN org_id TEXT",
            "ALTER TABLE review_candidates ADD COLUMN org_id TEXT",
            "ALTER TABLE review_history ADD COLUMN org_id TEXT",
            "ALTER TABLE jobs ADD COLUMN org_id TEXT",
            "ALTER TABLE idempotency_records ADD COLUMN org_id TEXT",
            """
            CREATE TABLE IF NOT EXISTS source_registry (
                source_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_family TEXT NOT NULL,
                display_name TEXT NOT NULL,
                connector_name TEXT NOT NULL,
                parser_name TEXT,
                parser_version TEXT,
                retention_policy_id TEXT,
                redaction_policy_id TEXT,
                trust_score REAL NOT NULL DEFAULT 0.5,
                pii_risk_level TEXT NOT NULL DEFAULT 'low',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS retention_rules (
                retention_policy_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                label TEXT NOT NULL,
                retention_days INTEGER NOT NULL,
                applies_to TEXT NOT NULL,
                action_on_expiry TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS redaction_rules (
                redaction_policy_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                label TEXT NOT NULL,
                pii_fields_json TEXT NOT NULL,
                masking_strategy TEXT NOT NULL,
                applies_to TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trust_scores (
                trust_score_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                score REAL NOT NULL,
                rationale TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(source_id) REFERENCES source_registry(source_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS lineage_edges (
                lineage_edge_id TEXT PRIMARY KEY,
                org_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                field_name TEXT,
                citation_span TEXT,
                field_confidence REAL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(source_id) REFERENCES source_registry(source_id)
            )
            """,
        ],
    ),
    (
        "003_graph_schema_metadata",
        [
            """
            CREATE TABLE IF NOT EXISTS graph_schema_metadata (
                graph_schema_version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL,
                notes_json TEXT NOT NULL
            )
            """
        ],
    ),
]


class RuntimeDatabase:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def migrate(self) -> list[str]:
        applied: list[str] = []
        with self.connect() as connection:
            existing = {
                row["name"]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchall()
            }
            if "schema_migrations" not in existing:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        migration_id TEXT PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
            applied_ids = {
                row["migration_id"]
                for row in connection.execute("SELECT migration_id FROM schema_migrations").fetchall()
            }
            for migration_id, statements in MIGRATIONS:
                if migration_id in applied_ids:
                    continue
                for statement in statements:
                    try:
                        connection.execute(statement)
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" in str(exc).lower():
                            continue
                        raise
                connection.execute(
                    "INSERT INTO schema_migrations (migration_id, applied_at) VALUES (?, ?)",
                    (migration_id, datetime.now(UTC).isoformat()),
                )
                applied.append(migration_id)
        return applied

    def health(self) -> dict[str, Any]:
        self.migrate()
        with self.connect() as connection:
            migrations = connection.execute("SELECT COUNT(*) AS count FROM schema_migrations").fetchone()["count"]
            return {
                "path": str(self.path),
                "migrations": migrations,
            }


def serialize_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def deserialize_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def build_runtime_db(settings: Settings) -> RuntimeDatabase:
    db = RuntimeDatabase(settings.runtime_db_path)
    db.migrate()
    return db
