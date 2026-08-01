from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, UTC
import hashlib
from typing import Any

from fastapi import Request

from app.core.runtime_db import RuntimeDatabase, deserialize_json, serialize_json


class RateLimiter:
    def __init__(self, request_limit: int, window_seconds: int):
        self.request_limit = request_limit
        self.window_seconds = window_seconds
        self.buckets: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, now_ts: float) -> bool:
        bucket = self.buckets[key]
        cutoff = now_ts - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.request_limit:
            return False
        bucket.append(now_ts)
        return True


class IdempotencyService:
    def __init__(self, runtime_db: RuntimeDatabase):
        self.db = runtime_db

    def request_hash(self, request: Request, body: bytes) -> str:
        payload = f"{request.method}|{request.url.path}|{body.decode('utf-8', errors='ignore')}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, idem_key: str, org_id: str | None = None) -> dict[str, Any] | None:
        with self.db.connect() as connection:
            if org_id:
                row = connection.execute(
                    "SELECT * FROM idempotency_records WHERE idem_key=? AND org_id=?",
                    (idem_key, org_id),
                ).fetchone()
            else:
                row = connection.execute("SELECT * FROM idempotency_records WHERE idem_key=?", (idem_key,)).fetchone()
        return dict(row) if row else None

    def store(self, idem_key: str, method: str, path: str, request_hash: str, response_payload: dict[str, Any], org_id: str | None = None) -> None:
        with self.db.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO idempotency_records (idem_key, method, path, request_hash, response_json, created_at, org_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    idem_key,
                    method,
                    path,
                    request_hash,
                    serialize_json(response_payload),
                    datetime.now(UTC).isoformat(),
                    org_id,
                ),
            )

    def load_response(self, record: dict[str, Any]) -> dict[str, Any]:
        return deserialize_json(record.get("response_json"), {})
