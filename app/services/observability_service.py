from __future__ import annotations

from collections import Counter, defaultdict, deque
from datetime import datetime, UTC
import json
from typing import Any

from app.core.config import Settings


class ObservabilityService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.counters = Counter()
        self.latencies = defaultdict(lambda: deque(maxlen=200))

    def log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "payload": payload,
        }
        self.settings.observability_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.settings.observability_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def record_request(self, path: str, status_code: int, duration_ms: float) -> None:
        self.counters["requests_total"] += 1
        self.counters[f"status_{status_code}"] += 1
        self.latencies[path].append(duration_ms)
        self.write_metrics_snapshot()

    def metrics(self) -> dict[str, Any]:
        return {
            "counters": dict(self.counters),
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
        self.settings.metrics_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.metrics_path.write_text(json.dumps(self.metrics(), indent=2), encoding="utf-8")
