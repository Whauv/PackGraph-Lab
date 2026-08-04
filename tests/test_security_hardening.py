from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services.private_data_service import PrivateDataService
from app.services.security_utils import sanitize_private_record_for_graph, sanitize_run_report, secure_write_json


class SecurityHardeningTests(unittest.TestCase):
    def test_sanitize_run_report_hashes_local_paths(self):
        report = {
            "json_source_dir": "C:/sensitive/private_data",
            "sqlite_path": "C:/sensitive/catalog.sqlite",
            "artifact_paths": {
                "report_path": "C:/sensitive/reports/run.json",
                "state_path": "C:/sensitive/state/run.json",
            },
            "backend_mode": {"neo4j_uri": "bolt://user:pass@localhost:7687"},
        }
        sanitized = sanitize_run_report(report)
        self.assertNotIn("json_source_dir", sanitized)
        self.assertNotIn("sqlite_path", sanitized)
        self.assertEqual(sanitized["artifact_paths"]["report_path"]["file_name"], "run.json")
        self.assertEqual(sanitized["backend_mode"]["neo4j_uri"], "bolt://localhost:7687")

    def test_graph_provenance_suppresses_sensitive_fields(self):
        row = {
            "private_record_id": "ROW-1",
            "provenance_id": "prov-1",
            "source_record_id": "json_dataset_1:1",
            "parser_name": "parser",
            "parser_version": "1.0",
            "source_name": "records.json",
            "source_url": "https://hidden.example",
            "file_path": "C:/very/private/records.json",
            "content_hash": "deadbeef",
        }
        sanitized = sanitize_private_record_for_graph(row)
        self.assertNotIn("source_url", sanitized)
        self.assertNotIn("file_path", sanitized)
        self.assertNotIn("content_hash", sanitized)
        self.assertIn("file_path_ref", sanitized)
        self.assertEqual(sanitized["source_name"], "records.json")

    def test_private_records_default_to_redacted_provenance(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            nested = root / "a" / "b"
            nested.mkdir(parents=True, exist_ok=True)
            (nested / "suppliers.json").write_text('[{"supplier_name":"Northstar Films","country":"Canada"}]', encoding="utf-8")
            service = PrivateDataService(root)
            rows = service.ingestable_records(run_id="ING-SEC")
            self.assertTrue(rows)
            first = rows[0]
            self.assertNotIn("source_url", first)
            self.assertIn("provenance", first)
            self.assertIn("path_ref", first["provenance"])

    def test_secure_write_json_creates_parent(self):
        with tempfile.TemporaryDirectory() as tempdir:
            target = Path(tempdir) / "nested" / "artifact.json"
            secure_write_json(target, {"status": "ok"})
            self.assertTrue(target.exists())
            self.assertIn('"status": "ok"', target.read_text(encoding="utf-8"))

    def test_requirements_have_no_openai_dependency(self):
        requirements = Path(__file__).resolve().parents[1] / "requirements.txt"
        content = requirements.read_text(encoding="utf-8").lower()
        self.assertNotIn("openai", content)


if __name__ == "__main__":
    unittest.main()
