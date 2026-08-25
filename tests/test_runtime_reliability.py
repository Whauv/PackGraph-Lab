from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.services.response_cache_service import ResponseCacheService
from app.services.runtime_maintenance_service import RuntimeMaintenanceService


class RuntimeReliabilityTests(unittest.TestCase):
    def test_response_cache_hits_and_invalidation(self):
        cache = ResponseCacheService()
        counter = {"count": 0}

        def load():
            counter["count"] += 1
            return {"value": counter["count"]}

        first = cache.get_or_set("route:test", {"query": "film"}, ttl_seconds=30, loader=load)
        second = cache.get_or_set("route:test", {"query": "film"}, ttl_seconds=30, loader=load)
        self.assertEqual(first, {"value": 1})
        self.assertEqual(second, {"value": 1})
        self.assertEqual(counter["count"], 1)

        cache.invalidate_prefix("route:test")
        third = cache.get_or_set("route:test", {"query": "film"}, ttl_seconds=30, loader=load)
        self.assertEqual(third, {"value": 2})
        self.assertEqual(counter["count"], 2)

    def test_runtime_maintenance_cleanup_is_safe(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            runtime_dir = root / "runtime"
            staging_dir = root / "staging"
            reports_dir = runtime_dir / "reports"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            staging_dir.mkdir(parents=True, exist_ok=True)
            reports_dir.mkdir(parents=True, exist_ok=True)

            old_report = reports_dir / "old.json"
            new_report = reports_dir / "new.json"
            old_report.write_text("old", encoding="utf-8")
            new_report.write_text("new", encoding="utf-8")
            stale_log = runtime_dir / "stale.jsonl"
            fresh_log = runtime_dir / "fresh.jsonl"
            stale_log.write_text("stale", encoding="utf-8")
            fresh_log.write_text("fresh", encoding="utf-8")
            stale_tmp = runtime_dir / "orphan.partial"
            stale_tmp.write_text("tmp", encoding="utf-8")

            old_epoch = time.time() - (9 * 24 * 60 * 60)
            os.utime(old_report, (old_epoch, old_epoch))
            os.utime(stale_log, (old_epoch, old_epoch))
            os.utime(stale_tmp, (old_epoch, old_epoch))

            settings = Settings(
                packgraph_runtime_dir=runtime_dir,
                packgraph_staging_dir=staging_dir,
                ingest_report_dir=reports_dir,
                cleanup_retention_days=7,
                cleanup_max_report_files=1,
                cleanup_max_runtime_logs=1,
            )
            service = RuntimeMaintenanceService(settings)
            result = service.cleanup()

            self.assertEqual(result["removed_count"], 3)
            self.assertFalse(old_report.exists())
            self.assertFalse(stale_log.exists())
            self.assertFalse(stale_tmp.exists())
            self.assertTrue(new_report.exists())
            self.assertTrue(fresh_log.exists())


class RuntimeApiReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        runtime_dir = root / "runtime"
        staging_dir = root / "staging"
        private_dir = root / "private"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        staging_dir.mkdir(parents=True, exist_ok=True)
        private_dir.mkdir(parents=True, exist_ok=True)
        os.environ["PACKGRAPH_RUNTIME_DIR"] = str(runtime_dir)
        os.environ["PACKGRAPH_STAGING_DIR"] = str(staging_dir)
        os.environ["PACKGRAPH_PRIVATE_DATA_DIR"] = str(private_dir)
        os.environ["PACKGRAPH_RUNTIME_DB_PATH"] = str(runtime_dir / "packgraph_runtime.db")
        os.environ["PACKGRAPH_PROJECT_MEMORY_PATH"] = str(staging_dir / "project_memory.json")
        os.environ["PACKGRAPH_REVIEW_CANDIDATES_PATH"] = str(staging_dir / "agent_review_candidates.json")
        os.environ["PACKGRAPH_AGENT_AUDIT_PATH"] = str(runtime_dir / "agent_audit.jsonl")
        os.environ["PACKGRAPH_REVIEW_AUDIT_PATH"] = str(runtime_dir / "review_audit.jsonl")
        os.environ["PACKGRAPH_ENTITY_RESOLUTION_AUDIT_PATH"] = str(runtime_dir / "entity_resolution_audit.jsonl")
        os.environ["PACKGRAPH_MATCH_DECISION_CACHE_PATH"] = str(runtime_dir / "match_decision_cache.json")
        os.environ["PACKGRAPH_OBSERVABILITY_LOG_PATH"] = str(runtime_dir / "app_events.jsonl")
        os.environ["PACKGRAPH_METRICS_PATH"] = str(runtime_dir / "metrics_snapshot.json")
        os.environ["PACKGRAPH_NEO4J_TEST_STUB"] = "true"
        os.environ["NEO4J_URI"] = "bolt://localhost:7687"
        os.environ["NEO4J_USER"] = "neo4j"
        os.environ["NEO4J_PASSWORD"] = "packgraph123"
        os.environ["NEO4J_DATABASE"] = "neo4j"
        from app.core.config import get_settings
        from app.repositories.data_store import get_data_store

        get_settings.cache_clear()
        get_data_store.cache_clear()
        from app.main import app

        self.client = TestClient(app)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_paginated_suppliers_and_runtime_maintenance(self):
        suppliers = self.client.get("/suppliers", params={"page": 1, "limit": 5})
        self.assertEqual(suppliers.status_code, 200)
        body = suppliers.json()
        self.assertEqual(len(body["data"]), 5)
        self.assertEqual(body["meta"]["page"], 1)
        self.assertTrue(body["meta"]["has_next"])

        maintenance = self.client.get("/runtime/maintenance")
        self.assertEqual(maintenance.status_code, 200)
        summary = maintenance.json()["data"]
        self.assertEqual(summary["profile"], "local-demo")
        self.assertIn("runtime", summary)


if __name__ == "__main__":
    unittest.main()
