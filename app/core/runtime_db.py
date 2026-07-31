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
                    connection.execute(statement)
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
