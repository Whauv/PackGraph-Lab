from __future__ import annotations

import unittest

from app.repositories.graph_repository import LocalGraphRepository
from app.services.scenario_engine import ScenarioEngine


class ScenarioEngineTests(unittest.TestCase):
    def setUp(self):
        self.repository = LocalGraphRepository()
        self.engine = ScenarioEngine(self.repository)

    def test_supplier_outage_returns_metrics(self):
        result = self.engine.run("supplier_outage", material_id="MAT-001", options={"scenario_type": "supplier_outage"})
        self.assertEqual(result["scenario"], "supplier_outage")
        self.assertIn("materials_impacted", result["metrics"])
        self.assertTrue(isinstance(result["impacts"], list))

    def test_regulation_activation_uses_pending_regulation(self):
        result = self.engine.run("regulation_activation", material_id="MAT-001", options={"scenario_type": "regulation_activation"})
        self.assertEqual(result["scenario"], "regulation_activation")
        self.assertIn("effective_date", result["metrics"])

    def test_cost_constraint_returns_constraint_status(self):
        result = self.engine.run(
            "cost_constraint",
            material_id="MAT-001",
            options={"scenario_type": "cost_constraint", "max_cost": 4.2, "percent_increase": 10},
        )
        self.assertEqual(result["scenario"], "cost_constraint")
        self.assertIn("within_constraint", result["metrics"])


if __name__ == "__main__":
    unittest.main()
