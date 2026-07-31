from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.services.entity_resolution_agent import EntityResolutionAgent


class EntityResolutionAgentTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.settings = Settings(
            packgraph_data_dir=root / "generated",
            packgraph_runtime_dir=root / "runtime",
            packgraph_staging_dir=root / "staging",
            private_data_dir=root / "private",
            json_ingest_dir=root / "private",
            project_memory_path=root / "staging" / "project_memory.json",
            review_candidates_path=root / "staging" / "agent_review_candidates.json",
            agent_audit_path=root / "runtime" / "agent_audit.jsonl",
            review_audit_path=root / "runtime" / "review_audit.jsonl",
            entity_resolution_audit_path=root / "runtime" / "entity_resolution_audit.jsonl",
            match_decision_cache_path=root / "runtime" / "match_decision_cache.json",
            er_review_threshold=0.6,
            er_auto_accept_threshold=0.85,
        )
        self.settings.packgraph_runtime_dir.mkdir(parents=True, exist_ok=True)
        self.settings.packgraph_staging_dir.mkdir(parents=True, exist_ok=True)
        self.settings.match_decision_cache_path.write_text("{}", encoding="utf-8")
        self.agent = EntityResolutionAgent(self.settings)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_synonym_and_unit_matching(self):
        result = self.agent.compare_records(
            {"entity_type": "supplier", "label": "Aluminium Works GmbH", "cost": "4.0 USD/kg"},
            {"entity_type": "supplier", "label": "Aluminum Works", "cost": "4 USD/kg"},
        )
        self.assertIn(result["decision"], {"auto_commit", "review_before_merge"})
        self.assertGreater(result["confidence"], 0.6)

    def test_cache_is_persisted(self):
        left = {"entity_type": "material", "label": "Polyethylene film", "recyclability": "82 %"}
        right = {"entity_type": "material", "label": "PE film", "recyclability": "81 %"}
        self.agent.compare_records(left, right)
        cache = json.loads(self.settings.match_decision_cache_path.read_text(encoding="utf-8"))
        self.assertTrue(cache)


if __name__ == "__main__":
    unittest.main()
