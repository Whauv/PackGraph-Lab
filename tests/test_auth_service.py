from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.core.runtime_db import build_runtime_db
from app.services.auth_service import AuthService


class AuthServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.settings = Settings(
            packgraph_data_dir=root / "generated",
            packgraph_runtime_dir=root / "runtime",
            packgraph_staging_dir=root / "staging",
            private_data_dir=root / "private",
            json_ingest_dir=root / "private",
            runtime_db_path=root / "runtime" / "packgraph_runtime.db",
            project_memory_path=root / "staging" / "project_memory.json",
            review_candidates_path=root / "staging" / "agent_review_candidates.json",
            agent_audit_path=root / "runtime" / "agent_audit.jsonl",
            review_audit_path=root / "runtime" / "review_audit.jsonl",
            entity_resolution_audit_path=root / "runtime" / "entity_resolution_audit.jsonl",
            match_decision_cache_path=root / "runtime" / "match_decision_cache.json",
            observability_log_path=root / "runtime" / "app_events.jsonl",
            metrics_path=root / "runtime" / "metrics_snapshot.json",
            auth_secret="test-secret",
        )
        self.settings.packgraph_runtime_dir.mkdir(parents=True, exist_ok=True)
        self.settings.packgraph_staging_dir.mkdir(parents=True, exist_ok=True)
        self.settings.project_memory_path.write_text("{}", encoding="utf-8")
        self.settings.review_candidates_path.write_text("[]", encoding="utf-8")
        self.settings.match_decision_cache_path.write_text("{}", encoding="utf-8")
        self.db = build_runtime_db(self.settings)
        self.auth = AuthService(self.settings, self.db)
        self.auth.ensure_seed()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_register_hashes_password_and_creates_session(self):
        user = self.auth.register("Test User", "test@example.com", "verysecure123", "explorer")
        self.assertIn("session_token", user)
        self.assertEqual(user["email"], "test@example.com")
        self.assertTrue(self.auth.current_user(user["session_token"]))

    def test_login_and_logout(self):
        result = self.auth.login("analyst@packgraph.local", "packgraph-demo")
        self.assertIsNotNone(result)
        token = result["session_token"]
        self.assertTrue(self.auth.current_user(token))
        self.auth.logout(token)
        self.assertIsNone(self.auth.current_user(token))


if __name__ == "__main__":
    unittest.main()
