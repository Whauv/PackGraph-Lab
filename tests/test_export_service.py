from __future__ import annotations

import unittest

from app.services.export_service import ExportService


class ExportServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = ExportService()
        self.payload = {
            "material": {
                "material_id": "MAT-001",
                "name": "Film A11",
                "category": "film",
                "composition": "PE, mPE",
                "compliance_state": "compliant",
                "sustainability_score": 78,
                "recyclability_score": 76,
                "compostability_score": 46,
                "cost_range": {"low": 3.25, "high": 4.66, "currency": "USD/kg"},
            },
            "suppliers": [{"name": "Sable Circuit Packaging", "esg_score": 71, "disruption_risk_score": 66}],
            "documents": [{"title": "Film A11 synthetic declaration"}],
            "test_reports": [{"title": "Film A11 barrier and seal validation"}],
            "alerts": [{"title": "Film A11 cost increased", "detail": "Price increased in 2026-Q3."}],
            "regulations": [{"name": "Food Contact Framework 2030", "active": False, "effective_date": "2026-10-01", "focus": "food-contact"}],
        }

    def test_executive_summary_csv_contains_material(self):
        content = self.service.executive_summary_csv(self.payload).decode("utf-8")
        self.assertIn("Film A11", content)
        self.assertIn("supplier_count", content)

    def test_compliance_pack_pdf_has_header(self):
        content = self.service.compliance_pack_pdf(self.payload)
        self.assertIn(b"PackGraph Lab Compliance Pack", content)


if __name__ == "__main__":
    unittest.main()
