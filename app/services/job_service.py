from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, UTC
import json
from typing import Any, Callable
from uuid import uuid4

from app.core.config import Settings
from app.core.runtime_db import RuntimeDatabase, deserialize_json, serialize_json


JobHandler = Callable[[dict[str, Any]], dict[str, Any]]


class JobService:
    def __init__(self, settings: Settings, runtime_db: RuntimeDatabase):
        self.settings = settings
        self.db = runtime_db
        self.handlers: dict[str, JobHandler] = {}

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        self.handlers[job_type] = handler

    def enqueue(
        self,
        *,
        job_type: str,
        payload: dict[str, Any],
        org_id: str | None = None,
        owner_id: str | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
        delay_seconds: int = 0,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self.db.connect() as connection:
            if idempotency_key:
                existing = connection.execute(
                    "SELECT * FROM jobs WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if existing:
                    return self._row_to_job(existing)
            record = {
                "job_id": f"JOB-{uuid4().hex[:10].upper()}",
                "job_type": job_type,
                "status": "queued",
                "org_id": org_id,
                "owner_id": owner_id,
                "payload_json": serialize_json(payload),
                "result_json": None,
                "error_code": None,
                "error_detail": None,
                "idempotency_key": idempotency_key,
                "attempts": 0,
                "max_attempts": max_attempts,
                "run_after": (now + timedelta(seconds=delay_seconds)).isoformat(),
                "dead_lettered_at": None,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, job_type, status, owner_id, payload_json, result_json, error_code, error_detail,
                    idempotency_key, attempts, max_attempts, run_after, dead_lettered_at, created_at, updated_at, org_id
                ) VALUES (
                    :job_id, :job_type, :status, :owner_id, :payload_json, :result_json, :error_code, :error_detail,
                    :idempotency_key, :attempts, :max_attempts, :run_after, :dead_lettered_at, :created_at, :updated_at, :org_id
                )
                """,
                record,
            )
        return self.get(record["job_id"])

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.db.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list(self, *, status: str | None = None, org_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = "SELECT * FROM jobs"
        params: tuple[Any, ...] = ()
        conditions = []
        if status:
            conditions.append("status=?")
            params = (*params, status)
        if org_id:
            conditions.append("org_id=?")
            params = (*params, org_id)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params = (*params, limit)
        with self.db.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_job(row) for row in rows]

    def process_next(self) -> dict[str, Any] | None:
        now = datetime.now(UTC).isoformat()
        with self.db.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM jobs
                WHERE status IN ('queued', 'retry')
                  AND run_after <= ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if not row:
                return None
            job = self._row_to_job(row)
            connection.execute(
                "UPDATE jobs SET status='running', attempts=attempts+1, updated_at=? WHERE job_id=?",
                (now, job["job_id"]),
            )
        return self._run_job(job["job_id"])

    def process_all_available(self, limit: int = 20) -> list[dict[str, Any]]:
        results = []
        for _ in range(limit):
            processed = self.process_next()
            if not processed:
                break
            results.append(processed)
        return results

    def summary(self, org_id: str | None = None) -> dict[str, Any]:
        with self.db.connect() as connection:
            if org_id:
                rows = connection.execute(
                    "SELECT status, COUNT(*) AS count FROM jobs WHERE org_id=? GROUP BY status",
                    (org_id,),
                ).fetchall()
            else:
                rows = connection.execute("SELECT status, COUNT(*) AS count FROM jobs GROUP BY status").fetchall()
        counts = Counter({row["status"]: row["count"] for row in rows})
        return {"total": sum(counts.values()), "by_status": dict(sorted(counts.items()))}

    def _run_job(self, job_id: str) -> dict[str, Any]:
        job = self.get(job_id)
        if not job:
            raise ValueError("Unknown job.")
        handler = self.handlers.get(job["job_type"])
        now = datetime.now(UTC).isoformat()
        if handler is None:
            return self._fail_job(job, "unknown_job_type", f"No handler registered for {job['job_type']}.", now)
        try:
            result = handler(job["payload"])
            with self.db.connect() as connection:
                connection.execute(
                    "UPDATE jobs SET status='completed', result_json=?, updated_at=? WHERE job_id=?",
                    (serialize_json(result), now, job_id),
                )
        except Exception as exc:
            return self._fail_job(job, "job_failed", str(exc), now)
        return self.get(job_id)

    def _fail_job(self, job: dict[str, Any], error_code: str, error_detail: str, now: str) -> dict[str, Any]:
        attempts = int(job["attempts"]) + 1
        max_attempts = int(job["max_attempts"])
        if attempts >= max_attempts:
            status = "dead_letter"
            dead_lettered_at = now
            run_after = job["run_after"]
        else:
            status = "retry"
            dead_lettered_at = None
            run_after = (datetime.now(UTC) + timedelta(seconds=attempts * 30)).isoformat()
        with self.db.connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status=?, error_code=?, error_detail=?, updated_at=?, run_after=?, dead_lettered_at=?
                WHERE job_id=?
                """,
                (status, error_code, error_detail, now, run_after, dead_lettered_at, job["job_id"]),
            )
        return self.get(job["job_id"])

    def _row_to_job(self, row: Any) -> dict[str, Any]:
        record = dict(row)
        return {
            **record,
            "payload": deserialize_json(record.get("payload_json"), {}),
            "result": deserialize_json(record.get("result_json"), None),
        }
