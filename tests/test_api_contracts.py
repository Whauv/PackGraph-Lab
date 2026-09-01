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

    def test_health_and_metrics_endpoints(self):
        self.assertEqual(self.client.get("/health/live").status_code, 200)
        self.assertEqual(self.client.get("/health/ready").status_code, 200)
        self.assertEqual(self.client.get("/health/graph").status_code, 200)
        self.client.get("/materials")
        metrics = self.client.get("/metrics")
        self.assertEqual(metrics.status_code, 200)
        operations = self.client.get("/operations/dashboard")
        self.assertEqual(operations.status_code, 200)
        operations_payload = operations.json()["data"]
        self.assertIn("health_cards", operations_payload)
        self.assertIn("review_backlog", operations_payload)
        self.assertIn("graph_freshness", operations_payload)

    def test_auth_and_jobs_contract(self):
        login = self.client.post("/auth/login", json={"email": "admin@packgraph.local", "password": "packgraph-demo"})
        self.assertEqual(login.status_code, 200)
        token = login.json()["data"]["session_token"]
        headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "job-create-1"}
        job = self.client.post("/jobs", json={"job_type": "evaluate_entity_resolution", "payload": {}}, headers=headers)
        self.assertEqual(job.status_code, 200)
        listed = self.client.get("/jobs", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(listed.status_code, 200)
        preset = self.client.post(
            "/workspaces",
            json={
                "name": "Supplier risk graph preset",
                "filters": {
                    "preset_type": "graph",
                    "graph_preset": "supply",
                    "graph_filter": "SUPPLIED_BY",
                    "supplier_id": "SUP-001",
                    "evidence_strength": "moderate",
                    "review_state": "not_requested",
                },
                "selected_material_ids": ["MAT-001"],
                "active_tab": "intelligence",
            },
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "workspace-preset-1"},
        )
        self.assertEqual(preset.status_code, 200)
        workspace_list = self.client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(workspace_list.status_code, 200)
        self.assertEqual(workspace_list.json()["data"][0]["filters"]["preset_type"], "graph")
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

    def test_query_ask_returns_structured_workflow_output(self):
        response = self.client.post(
            "/query/ask",
            json={
                "question": "compare Film A11 against alternatives",
                "options": {"material_id": "MAT-001"},
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertIn("panel", payload)
        self.assertIn("recommended_action", payload["panel"])
        self.assertIn("workflow", payload["panel"])
        self.assertEqual(payload["panel"]["recommended_action"]["target"], "workbench")
        self.assertEqual(payload["panel"]["workflow"]["current_stage"], "Compare")

    def test_source_intake_upload_profiles_and_feeds_chat(self):
        source_payload = {
            "materials": [
                {
                    "name": "Seaweed Laminate X9",
                    "category": "biofilm",
                    "supplier": "BlueKelp Materials",
                    "compostability_score": 91,
                }
            ]
        }
        upload = self.client.post(
            "/source-intake/upload",
            data={"source_type": "json", "title": "Seaweed laminate source"},
            files={"file": ("seaweed-source.json", json_bytes(source_payload), "application/json")},
        )
        self.assertEqual(upload.status_code, 200)
        upload_payload = upload.json()["data"]
        self.assertEqual(upload_payload["schema_profile"]["kind"], "json")
        self.assertGreater(upload_payload["schema_profile"]["field_count"], 0)
        source_id = upload_payload["source"]["source_id"]

        listed = self.client.get("/source-intake/sources")
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(any(item["source_id"] == source_id for item in listed.json()["data"]))

        answer = self.client.post("/query/ask", json={"question": "What source mentions Seaweed Laminate X9?"})
        self.assertEqual(answer.status_code, 200)
        answer_payload = answer.json()["data"]
        self.assertEqual(answer_payload["source"], "source_intake")
        self.assertTrue(answer_payload["rows"])
        self.assertEqual(answer_payload["rows"][0]["entity_type"], "uploaded_record")

    def test_validation_errors_are_normalized(self):
        response = self.client.post("/query/ask", json={"options": {}})
        self.assertEqual(response.status_code, 422)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"], "validation_error")
        self.assertEqual(payload["detail"], "Request validation failed.")
        self.assertTrue(payload["errors"])


def json_bytes(payload):
    import json

    return json.dumps(payload).encode("utf-8")


if __name__ == "__main__":
    unittest.main()
