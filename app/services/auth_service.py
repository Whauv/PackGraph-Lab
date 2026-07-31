from __future__ import annotations

from datetime import datetime, timedelta, UTC
import hashlib
import hmac
import json
import secrets
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.core.runtime_db import RuntimeDatabase, deserialize_json, serialize_json


class AuthService:
    ROLE_CONFIG = [
        {
            "role_id": "admin",
            "title": "Admin",
            "description": "Full product access across decision, review, moderation, and operations workflows.",
            "permissions": [
                "workspaces:write",
                "contributions:write",
                "contributions:review",
                "review:assign",
                "review:approve",
                "community:write",
                "community:moderate",
                "community:pin",
                "search:save",
                "notifications:view",
                "jobs:write",
                "jobs:view",
                "jobs:process",
                "documents:write",
                "exports:write",
            ],
        },
        {
            "role_id": "materials_strategist",
            "title": "Materials Strategist",
            "description": "Decision owner focused on shortlist, scenario, export, and investigation workflows.",
            "permissions": [
                "workspaces:write",
                "contributions:write",
                "community:write",
                "search:save",
                "notifications:view",
                "jobs:view",
                "documents:write",
                "exports:write",
            ],
        },
        {
            "role_id": "compliance_lead",
            "title": "Compliance Lead",
            "description": "Reviewer who can validate evidence, approve submissions, and moderate compliance-sensitive discussion.",
            "permissions": [
                "workspaces:write",
                "contributions:write",
                "contributions:review",
                "review:assign",
                "review:approve",
                "community:write",
                "community:moderate",
                "community:pin",
                "search:save",
                "notifications:view",
                "jobs:view",
                "documents:write",
                "exports:write",
            ],
        },
        {
            "role_id": "curator",
            "title": "Curator",
            "description": "Translator who shapes clearer evidence narratives and discussion framing.",
            "permissions": [
                "workspaces:write",
                "contributions:write",
                "community:write",
                "search:save",
                "notifications:view",
                "jobs:view",
            ],
        },
        {
            "role_id": "explorer",
            "title": "Explorer",
            "description": "Open user who can browse, discuss, and contribute structured findings.",
            "permissions": [
                "contributions:write",
                "community:write",
                "search:save",
                "notifications:view",
            ],
        },
    ]

    def __init__(self, settings: Settings, runtime_db: RuntimeDatabase):
        self.settings = settings
        self.db = runtime_db
        self.session_path = settings.packgraph_runtime_dir / "session.json"

    def _role_map(self) -> dict[str, dict[str, Any]]:
        return {role["role_id"]: role for role in self.ROLE_CONFIG}

    def _password_hash(self, password: str) -> str:
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            self.settings.auth_secret.encode("utf-8"),
            120000,
        )
        return digest.hex()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        return hmac.compare_digest(self._password_hash(password), password_hash)

    def _decorate_user(self, row: dict[str, Any] | Any) -> dict[str, Any]:
        row_dict = dict(row)
        role = self._role_map().get(row_dict.get("role_id"), self.ROLE_CONFIG[-1])
        return {
            "user_id": row_dict["user_id"],
            "org_id": row_dict["org_id"],
            "name": row_dict["name"],
            "email": row_dict["email"],
            "role_id": role["role_id"],
            "role_title": role["title"],
            "permissions": role["permissions"],
            "is_active": bool(row_dict.get("is_active", 1)),
        }

    def ensure_seed(self) -> None:
        with self.db.connect() as connection:
            org_count = connection.execute("SELECT COUNT(*) AS count FROM organizations").fetchone()["count"]
            if org_count == 0:
                connection.execute(
                    "INSERT INTO organizations (org_id, name, slug, created_at) VALUES (?, ?, ?, ?)",
                    ("ORG-001", "PackGraph Demo Org", "packgraph-demo", datetime.now(UTC).isoformat()),
                )
            user_count = connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
            if user_count == 0:
                seed_users = [
                    ("USR-001", "Demo Analyst", "analyst@packgraph.local", "packgraph-demo", "materials_strategist"),
                    ("USR-002", "Compliance Lead", "compliance@packgraph.local", "packgraph-demo", "compliance_lead"),
                    ("USR-003", "Community Curator", "curator@packgraph.local", "packgraph-demo", "curator"),
                    ("USR-004", "PackGraph Admin", "admin@packgraph.local", "packgraph-demo", "admin"),
                ]
                for user_id, name, email, password, role_id in seed_users:
                    connection.execute(
                        """
                        INSERT INTO users (user_id, org_id, name, email, password_hash, role_id, is_active, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            "ORG-001",
                            name,
                            email,
                            self._password_hash(password),
                            role_id,
                            1,
                            datetime.now(UTC).isoformat(),
                        ),
                    )
            if not self.session_path.exists():
                self.session_path.write_text("{}", encoding="utf-8")

    def list_roles(self) -> list[dict[str, Any]]:
        return self.ROLE_CONFIG

    def list_users(self) -> list[dict[str, Any]]:
        with self.db.connect() as connection:
            rows = connection.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        return [self._decorate_user(row) for row in rows]

    def register(self, name: str, email: str, password: str, role_id: str, org_id: str = "ORG-001") -> dict[str, Any]:
        role = self._role_map().get(role_id)
        if not role:
            raise ValueError("Unknown role.")
        normalized_email = email.strip().lower()
        now = datetime.now(UTC).isoformat()
        record = {
            "user_id": f"USR-{uuid4().hex[:8].upper()}",
            "org_id": org_id,
            "name": name.strip(),
            "email": normalized_email,
            "password_hash": self._password_hash(password),
            "role_id": role_id,
            "is_active": 1,
            "created_at": now,
        }
        try:
            with self.db.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO users (user_id, org_id, name, email, password_hash, role_id, is_active, created_at)
                    VALUES (:user_id, :org_id, :name, :email, :password_hash, :role_id, :is_active, :created_at)
                    """,
                    record,
                )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise ValueError("A user with that email already exists.") from exc
            raise
        session = self.create_session(record["user_id"])
        return {**self._decorate_user(record), "session_token": session["session_token"], "expires_at": session["expires_at"]}

    def create_session(self, user_id: str) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        created_at = datetime.now(UTC)
        expires_at = created_at + timedelta(hours=self.settings.session_ttl_hours)
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO sessions (session_token, user_id, created_at, expires_at, revoked_at, last_seen_at)
                VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (token, user_id, created_at.isoformat(), expires_at.isoformat(), created_at.isoformat()),
            )
        self.session_path.write_text(json.dumps({"session_token": token}), encoding="utf-8")
        return {"session_token": token, "expires_at": expires_at.isoformat()}

    def login(self, email: str, password: str) -> dict[str, Any] | None:
        with self.db.connect() as connection:
            user = connection.execute("SELECT * FROM users WHERE lower(email)=lower(?) AND is_active=1", (email.strip().lower(),)).fetchone()
        if not user or not self._verify_password(password, user["password_hash"]):
            return None
        session = self.create_session(user["user_id"])
        return {**self._decorate_user(user), **session}

    def logout(self, session_token: str | None = None) -> None:
        token = session_token or self._active_session_token()
        if token:
            with self.db.connect() as connection:
                connection.execute(
                    "UPDATE sessions SET revoked_at=?, last_seen_at=? WHERE session_token=?",
                    (datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat(), token),
                )
        self.session_path.write_text("{}", encoding="utf-8")

    def current_user(self, session_token: str | None = None) -> dict[str, Any] | None:
        token = session_token or self._active_session_token()
        if not token:
            return None
        now = datetime.now(UTC).isoformat()
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT users.*
                FROM sessions
                JOIN users ON users.user_id = sessions.user_id
                WHERE sessions.session_token = ?
                  AND sessions.revoked_at IS NULL
                  AND sessions.expires_at > ?
                  AND users.is_active = 1
                """,
                (token, now),
            ).fetchone()
            if row:
                connection.execute("UPDATE sessions SET last_seen_at=? WHERE session_token=?", (now, token))
        if not row:
            return None
        return self._decorate_user(row)

    def has_permission(self, user: dict[str, Any] | None, permission: str) -> bool:
        if not user:
            return False
        return permission in user.get("permissions", [])

    def list_workspaces(self, user_id: str | None) -> list[dict[str, Any]]:
        if not user_id:
            return []
        with self.db.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM workspaces WHERE user_id=? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [
            {
                "workspace_id": row["workspace_id"],
                "user_id": row["user_id"],
                "name": row["name"],
                "filters": deserialize_json(row["filters_json"], {}),
                "selected_material_ids": deserialize_json(row["selected_material_ids_json"], []),
                "active_tab": row["active_tab"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def save_workspace(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        workspace_id = f"WKS-{uuid4().hex[:8].upper()}"
        record = {
            "workspace_id": workspace_id,
            "user_id": user_id,
            "name": payload["name"],
            "filters_json": serialize_json(payload.get("filters", {})),
            "selected_material_ids_json": serialize_json(payload.get("selected_material_ids", [])),
            "active_tab": payload.get("active_tab", "materials"),
            "created_at": now,
            "updated_at": now,
        }
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO workspaces (workspace_id, user_id, name, filters_json, selected_material_ids_json, active_tab, created_at, updated_at)
                VALUES (:workspace_id, :user_id, :name, :filters_json, :selected_material_ids_json, :active_tab, :created_at, :updated_at)
                """,
                record,
            )
        return {**payload, "workspace_id": workspace_id, "user_id": user_id, "created_at": now, "updated_at": now}

    def list_saved_searches(self, user_id: str | None) -> list[dict[str, Any]]:
        if not user_id:
            return []
        with self.db.connect() as connection:
            rows = connection.execute("SELECT * FROM saved_searches WHERE user_id=? ORDER BY saved_at DESC", (user_id,)).fetchall()
        return [
            {
                "saved_search_id": row["saved_search_id"],
                "user_id": row["user_id"],
                "saved_at": row["saved_at"],
                **deserialize_json(row["payload_json"], {}),
            }
            for row in rows
        ]

    def save_search(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "saved_search_id": f"SRCH-{uuid4().hex[:8].upper()}",
            "user_id": user_id,
            "payload_json": serialize_json(payload),
            "saved_at": datetime.now(UTC).isoformat(),
        }
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT INTO saved_searches (saved_search_id, user_id, payload_json, saved_at)
                VALUES (:saved_search_id, :user_id, :payload_json, :saved_at)
                """,
                record,
            )
        return {"saved_search_id": record["saved_search_id"], "user_id": user_id, "saved_at": record["saved_at"], **payload}

    def _active_session_token(self) -> str | None:
        if not self.session_path.exists():
            return None
        try:
            payload = json.loads(self.session_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload.get("session_token")
