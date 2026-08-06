from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.core.runtime_db import build_runtime_db
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
            runtime_db_path=root / "runtime" / "packgraph_runtime.db",
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
        self.settings.match_decision_cache_path.write_text("{}", encoding="utf-8")
        self.runtime_db = build_runtime_db(self.settings)
        self.store = ReviewCandidateStore(self.settings, self.runtime_db)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_summary_export_and_import_apply(self):
        created = self.store.create(
            "entity_resolution",
            "Need review",
            {
                "display_name": "Film A11 duplicate",
                "comparison": {"left_label": "Film A11", "right_label": "Film A-11", "score_breakdown": {"lexical": 0.91}},
                "top_rows": [{"entity_type": "material", "label": "Film A11", "file_path": "C:/secret/materials.json", "source_url": "https://hidden.example"}],
                "provenance_snippets": ["Internal declaration paragraph"],
            },
        )
        summary = self.store.summary()
        self.assertEqual(summary["pending"], 1)

        export_path = Path(self.tempdir.name) / "pending.json"
        exported = self.store.export_pending(export_path)
        self.assertEqual(exported["count"], 1)
        exported_payload = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual(exported_payload[0]["display_name"], "Film A11 duplicate")
        self.assertIn("payload", exported_payload[0])
        self.assertNotIn("raw_payload", exported_payload[0]["payload"])
        self.assertNotIn("file_path", json.dumps(exported_payload[0]))
        self.assertNotIn("source_url", json.dumps(exported_payload[0]))

        csv_path = Path(self.tempdir.name) / "pending.csv"
        exported_csv = self.store.export_pending(csv_path)
        self.assertEqual(exported_csv["format"], "csv")
        self.assertIn("candidate_id", csv_path.read_text(encoding="utf-8"))

        raw_export_path = Path(self.tempdir.name) / "pending-raw.json"
        self.store.export_pending(raw_export_path, include_raw_props=True)
        raw_payload = json.loads(raw_export_path.read_text(encoding="utf-8"))
        self.assertIn("raw_payload", raw_payload[0]["payload"])

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
        audit_lines = self.settings.review_audit_path.read_text(encoding="utf-8").splitlines()
        self.assertTrue(audit_lines)
        self.assertNotIn("source_url", audit_lines[-1])
        self.assertNotIn("C:/secret/materials.json", audit_lines[0])


if __name__ == "__main__":
    unittest.main()
