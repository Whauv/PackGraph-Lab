from __future__ import annotations

import unittest

from scripts.ingest_graph import _deduplicate_rows, _redact_connection, normalize_neo4j_properties


class IngestGraphTests(unittest.TestCase):
    def test_normalize_flattens_nested_maps(self):
        normalized = normalize_neo4j_properties(
            {
                "material_id": "MAT-001",
                "cost_range": {"low": 3.25, "high": 4.66, "currency": "USD/kg"},
                "regions_available": ["Europe", "North America"],
            }
        )
        self.assertEqual(normalized["material_id"], "MAT-001")
        self.assertEqual(normalized["cost_range_low"], 3.25)
        self.assertEqual(normalized["cost_range_high"], 4.66)
        self.assertEqual(normalized["cost_range_currency"], "USD/kg")
        self.assertEqual(normalized["regions_available"], ["Europe", "North America"])

    def test_prewrite_deduplication_reports_removed_rows(self):
        rows, summary = _deduplicate_rows(
            [
                {"private_record_id": "PR-1", "content_hash": "abc"},
                {"private_record_id": "PR-1", "content_hash": "abc"},
                {"private_record_id": "PR-2", "content_hash": "def"},
            ]
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(summary["duplicates_removed"], 1)

    def test_redact_connection_hides_credentials(self):
        self.assertEqual(_redact_connection("bolt://neo4j:secret@localhost:7687"), "bolt://localhost:7687")


if __name__ == "__main__":
    unittest.main()
