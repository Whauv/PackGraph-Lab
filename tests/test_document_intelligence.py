from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.repositories.graph_repository import LocalGraphRepository
from app.services.document_intelligence_service import DocumentIntelligenceService


class DocumentIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.repository = LocalGraphRepository()
        self.service = DocumentIntelligenceService(Path(self.tempdir.name), self.repository)
        self.service.ensure_seed()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_upload_extracts_confidence_and_missing_fields(self):
        result = self.service.upload(
            filename="supplier-declaration.txt",
            content=b"Declaration\n2026-05-01\nFood contact compliant\nsupplier SUP-008\n",
            document_type="declaration",
            material_id="MAT-001",
            supplier_id="SUP-008",
            owner_id="USR-001",
        )
        record = result["record"]
        self.assertIn("extraction_confidence", record)
        self.assertIn("missing_fields", record)
        self.assertTrue(record["extraction_confidence"] >= 0.55)


if __name__ == "__main__":
    unittest.main()
