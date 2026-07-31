from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.services.agent_review import ReviewCandidateStore


class ReviewWorkflowTests(unittest.TestCase):
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
        )
        self.settings.packgraph_data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.packgraph_runtime_dir.mkdir(parents=True, exist_ok=True)
        self.settings.packgraph_staging_dir.mkdir(parents=True, exist_ok=True)
        self.settings.private_data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.project_memory_path.write_text("{}", encoding="utf-8")
        self.settings.review_candidates_path.write_text("[]", encoding="utf-8")
        self.settings.match_decision_cache_path.write_text("{}", encoding="utf-8")
        self.store = ReviewCandidateStore(self.settings)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_summary_export_and_import_apply(self):
        created = self.store.create("entity_resolution", "Need review", {"foo": "bar"})
        summary = self.store.summary()
        self.assertEqual(summary["pending"], 1)

        export_path = Path(self.tempdir.name) / "pending.json"
        exported = self.store.export_pending(export_path)
        self.assertEqual(exported["count"], 1)

        reviewed = [
            {
                "candidate_id": created["candidate_id"],
                "status": "approved",
                "review_notes": "Approved duplicate merge.",
                "match_pair_key": "left|right",
                "resolution_decision": "auto_commit",
                "left_label": "left",
                "right_label": "right",
                "confidence": 0.97,
            }
        ]
        reviewed_path = Path(self.tempdir.name) / "reviewed.json"
        reviewed_path.write_text(json.dumps(reviewed), encoding="utf-8")
        result = self.store.import_reviewed_decisions(reviewed_path, apply=True)
        self.assertEqual(result["applied"], 1)
        cache = json.loads(self.settings.match_decision_cache_path.read_text(encoding="utf-8"))
        self.assertIn("left|right", cache)


if __name__ == "__main__":
    unittest.main()
