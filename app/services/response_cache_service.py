from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable


class ResponseCacheService:
    def __init__(self):
        self._entries: dict[str, dict[str, Any]] = {}
        self._stats = {"hits": 0, "misses": 0, "sets": 0, "evictions": 0}

    def get_or_set(
        self,
        namespace: str,
        payload: Any,
        ttl_seconds: int,
        loader: Callable[[], Any],
    ) -> Any:
        now = time.time()
        key = self._key(namespace, payload)
        cached = self._entries.get(key)
        if cached and cached["expires_at"] > now:
            self._stats["hits"] += 1
            return cached["value"]
        if cached:
            self._entries.pop(key, None)
            self._stats["evictions"] += 1
        self._stats["misses"] += 1
        value = loader()
        self._entries[key] = {"value": value, "expires_at": now + max(1, ttl_seconds), "namespace": namespace}
        self._stats["sets"] += 1
        return value

    def invalidate_prefix(self, namespace_prefix: str) -> int:
        to_remove = [key for key, item in self._entries.items() if item["namespace"].startswith(namespace_prefix)]
        for key in to_remove:
            self._entries.pop(key, None)
        self._stats["evictions"] += len(to_remove)
        return len(to_remove)

    def prune(self) -> int:
        now = time.time()
        to_remove = [key for key, item in self._entries.items() if item["expires_at"] <= now]
        for key in to_remove:
            self._entries.pop(key, None)
        self._stats["evictions"] += len(to_remove)
        return len(to_remove)

    def stats(self) -> dict[str, Any]:
        return {**self._stats, "entries": len(self._entries)}

    def _key(self, namespace: str, payload: Any) -> str:
        try:
            encoded = json.dumps(payload, sort_keys=True, default=str)
        except TypeError:
            encoded = str(payload)
        digest = hashlib.sha256(f"{namespace}:{encoded}".encode("utf-8")).hexdigest()[:24]
        return f"{namespace}:{digest}"
