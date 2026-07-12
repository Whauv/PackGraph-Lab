from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AuthService:
    def __init__(self, runtime_dir: Path):
        self.users_path = runtime_dir / "users.json"
        self.workspaces_path = runtime_dir / "workspaces.json"
        self.session_path = runtime_dir / "session.json"

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

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
                        "role": "materials strategist",
                    },
                    {
                        "user_id": "USR-002",
                        "name": "Compliance Lead",
                        "email": "compliance@packgraph.local",
                        "password": "packgraph-demo",
                        "role": "compliance lead",
                    },
                ],
            )
        if not self.workspaces_path.exists():
            self._write_json(self.workspaces_path, [])
        if not self.session_path.exists():
            self._write_json(self.session_path, {"user_id": "USR-001"})

    def login(self, email: str, password: str) -> dict[str, Any] | None:
        users = self._read_json(self.users_path, [])
        user = next((item for item in users if item["email"] == email and item["password"] == password), None)
        if not user:
            return None
        self._write_json(self.session_path, {"user_id": user["user_id"]})
        return self.current_user()

    def current_user(self) -> dict[str, Any] | None:
        users = self._read_json(self.users_path, [])
        session = self._read_json(self.session_path, {})
        user = next((item for item in users if item["user_id"] == session.get("user_id")), None)
        if not user:
            return None
        return {key: value for key, value in user.items() if key != "password"}

    def list_workspaces(self, user_id: str | None) -> list[dict[str, Any]]:
        workspaces = self._read_json(self.workspaces_path, [])
        if not user_id:
            return []
        return [item for item in workspaces if item["user_id"] == user_id]

    def save_workspace(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        workspaces = self._read_json(self.workspaces_path, [])
        record = {"workspace_id": f"WKS-{len(workspaces) + 1:03d}", "user_id": user_id, **payload}
        workspaces.append(record)
        self._write_json(self.workspaces_path, workspaces)
        return record
