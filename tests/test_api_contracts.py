from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class ApiContractTests(unittest.TestCase):
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
        os.environ["GRAPH_BACKEND"] = "local"
        from app.core.config import get_settings
        from app.repositories.data_store import get_data_store

        get_settings.cache_clear()
        get_data_store.cache_clear()
        from app.main import app

        self.client = TestClient(app)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_health_and_metrics_endpoints(self):
        self.assertEqual(self.client.get("/health/live").status_code, 200)
        self.assertEqual(self.client.get("/health/ready").status_code, 200)
        self.client.get("/materials")
        metrics = self.client.get("/metrics")
        self.assertEqual(metrics.status_code, 200)

    def test_auth_and_jobs_contract(self):
        login = self.client.post("/auth/login", json={"email": "admin@packgraph.local", "password": "packgraph-demo"})
        self.assertEqual(login.status_code, 200)
        token = login.json()["data"]["session_token"]
        headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "job-create-1"}
        job = self.client.post("/jobs", json={"job_type": "evaluate_entity_resolution", "payload": {}}, headers=headers)
        self.assertEqual(job.status_code, 200)
        listed = self.client.get("/jobs", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(listed.status_code, 200)
        memory = self.client.patch(
            "/project-memory",
            json={"saved_entities": ["MAT-001"], "prior_questions": ["Recommend a food-safe recyclable film."]},
        )
        self.assertEqual(memory.status_code, 200)
        self.assertIn("MAT-001", memory.json()["data"]["saved_entities"])
        search = self.client.get("/search/command", params={"query": "snack"}, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(search.status_code, 200)
        self.assertIn("results", search.json()["data"])
        review = self.client.post(
            "/review-candidates/manual",
            json={"candidate_type": "material_decision", "reason": "Manual UI review", "payload": {"entity_id": "MAT-001"}},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(review.status_code, 200)
        self.assertEqual(review.json()["data"]["candidate_type"], "material_decision")
        investigation = self.client.post(
            "/investigations",
            json={
                "title": "Case workspace",
                "focus_material_id": "MAT-001",
                "notes": "Case note",
                "shortlisted_material_ids": ["MAT-001"],
                "comparison_material_ids": ["MAT-001"],
                "decision_rationale": "Initial recommendation.",
                "owner_name": "Demo Analyst",
                "due_date": "2026-09-12",
                "project_status": "active",
                "archived": False,
                "decision_history": [],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(investigation.status_code, 200)
        self.assertEqual(investigation.json()["data"]["owner_name"], "Demo Analyst")
        self.assertEqual(investigation.json()["data"]["project_status"], "active")

    def test_query_ask_accepts_context_payload(self):
        response = self.client.post(
            "/query/ask",
            json={
                "question": "show suppliers for this",
                "options": {"material_id": "MAT-001"},
                "context": {
                    "entity_type": "material",
                    "entity_id": "MAT-001",
                    "entity_name": "Film A11",
                    "metadata": {"category": "film"},
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(payload["plan"]["intent"], "suppliers_for_material")
        self.assertIn("resolved_question", payload)
        self.assertTrue(payload["rows"])


if __name__ == "__main__":
    unittest.main()
