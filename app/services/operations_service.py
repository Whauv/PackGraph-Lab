from __future__ import annotations

from typing import Any


class OperationsService:
    def __init__(self, state: Any):
        self.state = state

    def dashboard(self, org_id: str | None = None) -> dict[str, Any]:
        metrics = self.state.observability.metrics()
        review = self.state.review_store.summary(org_id=org_id)
        jobs = self.state.jobs.summary(org_id=org_id)
        runtime = self.state.runtime_maintenance.summary()
        graph = self.state.repository.graph_health()
        latency_paths = metrics.get("latency_ms", {})
        slowest = sorted(
            [{"path": path, **payload} for path, payload in latency_paths.items()],
            key=lambda item: item.get("avg", 0),
            reverse=True,
        )[:5]
        return {
            "health_cards": [
                {"label": "Query latency", "value": self._latency_label(slowest), "tone": self._latency_tone(slowest)},
                {"label": "Ingest health", "value": self._job_value(jobs), "tone": self._job_tone(jobs)},
                {"label": "Review backlog", "value": review.get("pending", 0), "tone": "warn" if review.get("pending", 0) else "good"},
                {"label": "Graph freshness", "value": graph.get("database", "neo4j"), "tone": "good" if graph.get("available", True) else "risk"},
                {"label": "Failed jobs", "value": jobs.get("by_status", {}).get("dead_letter", 0), "tone": "risk" if jobs.get("by_status", {}).get("dead_letter", 0) else "good"},
            ],
            "query_latency": slowest,
            "ingest_health": jobs,
            "review_backlog": review,
            "graph_freshness": graph,
            "runtime_artifacts": {
                "runtime_files": runtime.get("runtime", {}).get("file_count", 0),
                "staging_files": runtime.get("staging", {}).get("file_count", 0),
                "report_files": runtime.get("reports", {}).get("file_count", 0),
            },
            "artifact_locations": runtime.get("paths", {}),
        }

    def _latency_label(self, slowest: list[dict[str, Any]]) -> str:
        if not slowest:
            return "No traffic"
        return f"{slowest[0].get('avg', 0)} ms avg"

    def _latency_tone(self, slowest: list[dict[str, Any]]) -> str:
        if not slowest:
            return "neutral"
        avg = float(slowest[0].get("avg", 0) or 0)
        if avg >= 900:
            return "risk"
        if avg >= 400:
            return "warn"
        return "good"

    def _job_value(self, jobs: dict[str, Any]) -> str:
        by_status = jobs.get("by_status", {})
        return f"{by_status.get('completed', 0)} done / {by_status.get('queued', 0)} queued"

    def _job_tone(self, jobs: dict[str, Any]) -> str:
        by_status = jobs.get("by_status", {})
        if by_status.get("dead_letter", 0):
            return "risk"
        if by_status.get("retry", 0) or by_status.get("queued", 0):
            return "warn"
        return "good"
