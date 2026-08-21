from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import datetime, UTC
from typing import Any

from app.core.config import Settings
from app.services.security_utils import sanitize_audit_payload, secure_append_jsonl, secure_write_json


class ObservabilityService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.counters = Counter()
        self.latencies = defaultdict(lambda: deque(maxlen=200))
        self.gauges: dict[str, Any] = {}

    def log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        entry = sanitize_audit_payload({
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "payload": payload,
        })
        secure_append_jsonl(self.settings.observability_log_path, entry)

    def record_request(self, path: str, status_code: int, duration_ms: float) -> None:
        self.counters["requests_total"] += 1
        self.counters[f"status_{status_code}"] += 1
        self.latencies[path].append(duration_ms)
        self.write_metrics_snapshot()

    def record_cache(self, namespace: str, outcome: str) -> None:
        self.counters[f"cache_{outcome}_total"] += 1
        self.counters[f"cache_{namespace}_{outcome}_total"] += 1

    def record_job(self, status: str) -> None:
        self.counters[f"jobs_{status}_total"] += 1

    def set_gauge(self, key: str, value: Any) -> None:
        self.gauges[key] = value
        self.write_metrics_snapshot()

    def metrics(self) -> dict[str, Any]:
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "latency_ms": {
                path: {
                    "count": len(values),
                    "avg": round(sum(values) / len(values), 2) if values else 0.0,
                    "max": round(max(values), 2) if values else 0.0,
                }
                for path, values in self.latencies.items()
            },
        }

    def write_metrics_snapshot(self) -> None:
        secure_write_json(self.settings.metrics_path, self.metrics())
