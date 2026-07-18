from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class AuthService:
    ROLE_CONFIG = [
        {
            "role_id": "admin",
            "title": "Admin",
            "description": "Full local product access across decision, review, and moderation workflows.",
            "permissions": [
                "workspaces:write",
                "contributions:write",
                "contributions:review",
                "community:write",
                "community:moderate",
                "community:pin",
                "search:save",
                "notifications:view",
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
                "community:write",
                "community:moderate",
                "community:pin",
                "search:save",
                "notifications:view",
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

    def __init__(self, runtime_dir: Path):
        self.users_path = runtime_dir / "users.json"
        self.workspaces_path = runtime_dir / "workspaces.json"
        self.session_path = runtime_dir / "session.json"
        self.saved_searches_path = runtime_dir / "saved_searches.json"

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def _role_map(self) -> dict[str, dict[str, Any]]:
        return {role["role_id"]: role for role in self.ROLE_CONFIG}

    def _decorate_user(self, user: dict[str, Any]) -> dict[str, Any]:
        role = self._role_map().get(user.get("role_id") or user.get("role"), self.ROLE_CONFIG[-1])
        return {
            "user_id": user["user_id"],
            "name": user["name"],
            "email": user["email"],
            "role_id": role["role_id"],
            "role_title": role["title"],
            "permissions": role["permissions"],
        }

    def ensure_seed(self) -> None:
        if not self.users_path.exists():
            self._write_json(
                self.users_path,
                [
                    {
                        "user_id": "USR-001",
                        "name": "Demo Analyst",
                        "email": "analyst@packgraph.local",
                        "password": "packgraph-demo",
                        "role_id": "materials_strategist",
                    },
                    {
                        "user_id": "USR-002",
                        "name": "Compliance Lead",
                        "email": "compliance@packgraph.local",
                        "password": "packgraph-demo",
                        "role_id": "compliance_lead",
                    },
                    {
                        "user_id": "USR-003",
                        "name": "Community Curator",
                        "email": "curator@packgraph.local",
                        "password": "packgraph-demo",
                        "role_id": "curator",
                    },
                    {
                        "user_id": "USR-004",
                        "name": "PackGraph Admin",
                        "email": "admin@packgraph.local",
                        "password": "packgraph-demo",
                        "role_id": "admin",
                    },
                ],
            )
        if not self.workspaces_path.exists():
            self._write_json(self.workspaces_path, [])
        if not self.session_path.exists():
            self._write_json(self.session_path, {"user_id": "USR-001"})
        if not self.saved_searches_path.exists():
            self._write_json(self.saved_searches_path, [])

    def list_roles(self) -> list[dict[str, Any]]:
        return self.ROLE_CONFIG

    def list_users(self) -> list[dict[str, Any]]:
        return [self._decorate_user(item) for item in self._read_json(self.users_path, [])]

    def register(self, name: str, email: str, password: str, role_id: str) -> dict[str, Any]:
        users = self._read_json(self.users_path, [])
        normalized_email = email.strip().lower()
        if any(item["email"].lower() == normalized_email for item in users):
            raise ValueError("A user with that email already exists.")
        role = self._role_map().get(role_id)
        if not role:
            raise ValueError("Unknown role.")
        record = {
            "user_id": f"USR-{len(users) + 1:03d}",
            "name": name.strip(),
            "email": normalized_email,
            "password": password,
            "role_id": role_id,
        }
        users.append(record)
        self._write_json(self.users_path, users)
        self._write_json(self.session_path, {"user_id": record["user_id"]})
        return self._decorate_user(record)

    def login(self, email: str, password: str) -> dict[str, Any] | None:
        users = self._read_json(self.users_path, [])
        user = next((item for item in users if item["email"].lower() == email.lower() and item["password"] == password), None)
        if not user:
            return None
        self._write_json(self.session_path, {"user_id": user["user_id"]})
        return self._decorate_user(user)

    def logout(self) -> None:
        self._write_json(self.session_path, {})

    def current_user(self) -> dict[str, Any] | None:
        users = self._read_json(self.users_path, [])
        session = self._read_json(self.session_path, {})
        user = next((item for item in users if item["user_id"] == session.get("user_id")), None)
        if not user:
            return None
        return self._decorate_user(user)

    def has_permission(self, user: dict[str, Any] | None, permission: str) -> bool:
        if not user:
            return False
        return permission in user.get("permissions", [])

    def list_workspaces(self, user_id: str | None) -> list[dict[str, Any]]:
        workspaces = self._read_json(self.workspaces_path, [])
        if not user_id:
            return []
        return sorted(
            [item for item in workspaces if item["user_id"] == user_id],
            key=lambda item: item.get("updated_at", item.get("created_at", "")),
            reverse=True,
        )

    def save_workspace(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        workspaces = self._read_json(self.workspaces_path, [])
        now = datetime.now().isoformat(timespec="seconds")
        record = {
            "workspace_id": f"WKS-{len(workspaces) + 1:03d}",
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            **payload,
        }
        workspaces.append(record)
        self._write_json(self.workspaces_path, workspaces)
        return record

    def list_saved_searches(self, user_id: str | None) -> list[dict[str, Any]]:
        searches = self._read_json(self.saved_searches_path, [])
        if not user_id:
            return []
        return sorted(
            [item for item in searches if item["user_id"] == user_id],
            key=lambda item: item.get("saved_at", ""),
            reverse=True,
        )

    def save_search(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        searches = self._read_json(self.saved_searches_path, [])
        record = {
            "saved_search_id": f"SRCH-{len(searches) + 1:03d}",
            "user_id": user_id,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            **payload,
        }
        searches.append(record)
        self._write_json(self.saved_searches_path, searches)
        return record
