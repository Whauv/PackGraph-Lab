from __future__ import annotations

from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.services.ingest_sources import resolve_ingest_sources
from app.services.private_data_service import PrivateDataService


class IngestSourceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.json_dir = root / "json"
        self.json_dir.mkdir(parents=True, exist_ok=True)
        nested = self.json_dir / "nested" / "suppliers"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "records.json").write_text(
            json.dumps(
                [
                    {"supplier_name": "Aluminium Works GmbH", "country": "Germany", "material": "aluminium"},
                    {"supplier_name": "Aluminium Works GmbH", "country": "Germany", "material": "aluminium"},
                ]
            ),
            encoding="utf-8",
        )
        (self.json_dir / "broken.json").write_text("{", encoding="utf-8")

        self.sqlite_path = root / "records.sqlite"
        with closing(sqlite3.connect(self.sqlite_path)) as connection:
            connection.execute("CREATE TABLE suppliers (supplier_name TEXT, country TEXT, cost TEXT)")
            connection.execute("INSERT INTO suppliers VALUES ('PE Supply Co', 'USA', '4.2 USD/kg')")
            connection.commit()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_resolve_ingest_sources_prefers_cli(self):
        settings = Settings(json_ingest_dir=Path("env-json"), sqlite_ingest_path=Path("env.sqlite"))
        selection = resolve_ingest_sources(settings, json_source_dir=self.json_dir, sqlite_path=self.sqlite_path)
        self.assertEqual(selection.selection_source, "cli")
        self.assertEqual(selection.json_source_dir, self.json_dir)
        self.assertEqual(selection.sqlite_path, self.sqlite_path)

    def test_private_service_profiles_recursive_json_and_sqlite(self):
        service = PrivateDataService(self.json_dir, self.sqlite_path)
        summary = service.inspect_schema()
        self.assertTrue(summary["private_data_active"])
        self.assertGreaterEqual(summary["dataset_count"], 2)
        self.assertEqual(summary["source_profile"]["json_files_scanned"], 2)
        self.assertEqual(summary["source_profile"]["sqlite_tables_scanned"], 1)
        self.assertTrue(summary["source_profile"]["invalid_sources"])
        self.assertTrue(summary["source_profile"]["duplicate_content_report"])
        self.assertIn("nested_folder_depth_summary", summary["source_profile"])
        self.assertTrue(summary["source_profile"]["validation_errors"] or summary["source_profile"]["parse_errors"])

    def test_ingestable_records_include_provenance_metadata(self):
        service = PrivateDataService(self.json_dir, self.sqlite_path, parser_name="tester", parser_version="9.9")
        rows = service.ingestable_records(run_id="ING-TEST")
        self.assertTrue(rows)
        first = rows[0]
        self.assertIn("provenance_id", first)
        self.assertIn("source_record_id", first)
        self.assertEqual(first["parser_name"], "tester")
        self.assertEqual(first["parser_version"], "9.9")
        self.assertEqual(first["run_id"], "ING-TEST")
        self.assertIn("schema_version", first)
        self.assertIn("file_size_bytes", first)


if __name__ == "__main__":
    unittest.main()
