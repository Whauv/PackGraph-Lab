from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.config import get_settings
from app.repositories.data_store import get_data_store
from app.repositories.graph_repository import LocalGraphRepository
from app.services.query_engine import QueryEngine


class AgenticQueryEngineTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        runtime_dir = root / "runtime"
        staging_dir = root / "staging"
        data_dir = root / "generated"
        private_dir = root / "private"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        staging_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)
        private_dir.mkdir(parents=True, exist_ok=True)

        get_settings.cache_clear()
        get_data_store.cache_clear()
        import os

        os.environ["PACKGRAPH_RUNTIME_DIR"] = str(runtime_dir)
        os.environ["PACKGRAPH_STAGING_DIR"] = str(staging_dir)
        os.environ["PACKGRAPH_PRIVATE_DATA_DIR"] = str(private_dir)
        os.environ["PACKGRAPH_PROJECT_MEMORY_PATH"] = str(staging_dir / "project_memory.json")
        os.environ["PACKGRAPH_REVIEW_CANDIDATES_PATH"] = str(staging_dir / "agent_review_candidates.json")
        os.environ["PACKGRAPH_AGENT_AUDIT_PATH"] = str(runtime_dir / "agent_audit.jsonl")
        os.environ["PACKGRAPH_RUNTIME_DB_PATH"] = str(runtime_dir / "packgraph_runtime.db")
        os.environ["GRAPH_BACKEND"] = "local"

    def tearDown(self):
        get_settings.cache_clear()
        get_data_store.cache_clear()
        self.tempdir.cleanup()

    def test_query_returns_agent_fields_and_updates_memory(self):
        repository = LocalGraphRepository()
        engine = QueryEngine(repository)

        payload = engine.ask("find recyclable substitutes for Film A11 with proof")

        self.assertIn("agent_state_machine", payload)
        self.assertIn("agent_tools", payload)
        self.assertIn("agent_orchestration", payload)
        self.assertIn("investigation_plan", payload)
        self.assertIn("evidence_profile", payload)
        self.assertIn("project_memory", payload)
        self.assertIn("entity_resolution", payload)
        self.assertTrue(any(item["name"] == "classify_question" for item in payload["agent_tools"]))
        self.assertTrue(any(item["name"] == "retrieve_source_documents" for item in payload["agent_tools"]))
        self.assertTrue(payload["project_memory"]["prior_questions"])


if __name__ == "__main__":
    unittest.main()
