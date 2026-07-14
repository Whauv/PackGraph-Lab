from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.repositories.graph_repository import LocalGraphRepository
from app.services.scenario_history_service import ScenarioHistoryService


class RepositoryExtensionTests(unittest.TestCase):
    def setUp(self):
        self.repository = LocalGraphRepository()

    def test_global_search_returns_materials(self):
        results = self.repository.global_search("film a11")
        self.assertTrue(any(item["entity_type"] == "material" for item in results))

    def test_supplier_detail_contains_trends(self):
        supplier_id = self.repository.suppliers[0]["supplier_id"]
        supplier = self.repository.get_supplier(supplier_id)
        self.assertIsNotNone(supplier)
        self.assertIn("risk_trend", supplier)
        self.assertIn("supplied_materials", supplier)

    def test_regulation_detail_contains_actions(self):
        regulation_id = self.repository.regulations[0]["regulation_id"]
        regulation = self.repository.get_regulation(regulation_id)
        self.assertIsNotNone(regulation)
        self.assertIn("affected_materials", regulation)
        self.assertIn("likely_actions", regulation)


class ScenarioHistoryTests(unittest.TestCase):
    def test_save_and_list_history(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = ScenarioHistoryService(Path(temp_dir))
            service.save(
                scenario_type="supplier_outage",
                material_id="MAT-001",
                supplier_id="SUP-001",
                options={"scope": "material"},
                result={"summary": "ok", "metrics": {"materials_impacted": 1}, "actions": [], "impacts": [{}]},
                owner_id="USR-001",
            )
            records = service.list("USR-001")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["scenario_type"], "supplier_outage")


if __name__ == "__main__":
    unittest.main()
