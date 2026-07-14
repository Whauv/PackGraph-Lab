from __future__ import annotations

import unittest

from scripts.ingest_graph import normalize_neo4j_properties


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


if __name__ == "__main__":
    unittest.main()
