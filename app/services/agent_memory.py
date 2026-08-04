from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings
from app.services.security_utils import secure_write_json


class ProjectMemoryStore:
    def __init__(self, settings: Settings):
        self.path = settings.project_memory_path

    def load(self) -> dict[str, Any]:
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def update(self, patch: dict[str, list[Any]]) -> dict[str, Any]:
        memory = self.load()
        for key, values in patch.items():
            existing = memory.setdefault(key, [])
            for value in values:
                if value is None or value == "" or value == []:
                    continue
                if value not in existing:
                    existing.append(value)
        secure_write_json(self.path, memory)
        return memory
