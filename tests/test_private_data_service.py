from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.repositories.graph_repository import LocalGraphRepository
from app.services.private_data_service import PrivateDataService
from app.services.query_engine import QueryEngine


class PrivateDataServiceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.private_dir = Path(self.tempdir.name)
        nested = self.private_dir / "region-a" / "suppliers"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "records.json").write_text(
            json.dumps(
                [
                    {"supplier_name": "Aluminum Works GmbH", "country": "Germany", "material": "aluminum", "grade": "A"},
                    {"supplier_name": "Steel Source SARL", "country": "France", "material": "steel", "grade": "B"},
                ]
            ),
            encoding="utf-8",
        )
        self.service = PrivateDataService(self.private_dir)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_schema_summary_hides_paths_and_values(self):
        summary = self.service.inspect_schema()
        self.assertTrue(summary["private_data_active"])
        self.assertEqual(summary["dataset_count"], 1)
        serialized = json.dumps(summary)
        self.assertNotIn("records.json", serialized)
        self.assertNotIn("Aluminum Works GmbH", serialized)

    def test_private_query_matches_keywords_and_location(self):
        result = self.service.query("find aluminum suppliers in germany")
        self.assertTrue(result["rows"])
        self.assertEqual(result["rows"][0]["entity_type"], "supplier")
        self.assertIn("Aluminum Works", result["rows"][0]["label"])


class HybridQueryEngineTests(unittest.TestCase):
    def test_query_engine_prefers_private_data_when_present(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            private_dir = Path(temp_dir)
            (private_dir / "private.json").write_text(
                json.dumps([{"supplier_name": "Aluminum Works GmbH", "country": "Germany", "material": "aluminum"}]),
                encoding="utf-8",
            )
            repository = LocalGraphRepository()
            engine = QueryEngine(repository, PrivateDataService(private_dir))
            payload = engine.ask("find aluminum suppliers in germany")
            self.assertEqual(payload["source"], "private_data")
            self.assertTrue(payload["private_data_active"])
            self.assertTrue(payload["rows"])
            self.assertIn("pipeline_trace", payload)


if __name__ == "__main__":
    unittest.main()
