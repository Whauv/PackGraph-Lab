from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.repositories.graph_repository import LocalGraphRepository
from app.services.component_discovery_service import ComponentDiscoveryService


class ComponentDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self.tempdir.name)
        self.repository = LocalGraphRepository()
        self.fetch_calls = 0

        def fake_fetcher(url: str):
            self.fetch_calls += 1
            if "opensearch" in url:
                return ["ethylene vinyl alcohol", ["Ethylene vinyl alcohol"], [""], ["https://example.test/evoh"]]
            return {
                "title": "Ethylene vinyl alcohol",
                "extract": "Ethylene vinyl alcohol is a barrier polymer used in packaging structures.",
                "description": "barrier polymer",
                "type": "standard",
                "content_urls": {"desktop": {"page": "https://example.test/evoh"}},
            }

        self.service = ComponentDiscoveryService(self.runtime_dir, self.repository, fetcher=fake_fetcher)
        self.service.ensure_seed()
        self.repository.runtime_components_path = self.runtime_dir / "discovered_components.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_discover_saves_component_for_future_lookup(self):
        discovered = self.service.discover("ethylene vinyl alcohol")
        self.assertIsNotNone(discovered)
        self.assertEqual(discovered["discovery_state"], "newly_discovered")
        self.assertEqual(discovered["record"]["name"], "Ethylene vinyl alcohol")
        self.assertTrue((self.runtime_dir / "discovered_components.json").exists())

        cached = self.service.discover("ethylene vinyl alcohol")
        self.assertEqual(cached["discovery_state"], "cached")
        self.assertEqual(self.fetch_calls, 2)

    def test_repository_global_search_reads_cached_components(self):
        payload = [
            {
                "component_id": "CMP-001",
                "name": "Ethylene vinyl alcohol",
                "normalized_name": "ethylene vinyl alcohol",
                "summary": "Barrier polymer for packaging films.",
                "component_type": "barrier polymer",
                "source_name": "Wikipedia",
                "source_url": "https://example.test/evoh",
                "source_type": "web_discovery",
                "aliases": ["EVOH"],
                "tags": ["Wikipedia", "barrier"],
                "related_material_ids": [],
                "key_facts": [],
                "discovered_at": "2026-07-22T10:00:00",
            }
        ]
        (self.runtime_dir / "discovered_components.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

        results = self.repository.global_search("evoh")
        self.assertTrue(any(item["entity_type"] == "component" for item in results))

    def test_discover_with_related_from_image_filename(self):
        payload = self.service.discover_with_related(filename="evoh-film-reference.png", content=b"")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["identification"]["method"], "image_filename_inference")
        self.assertTrue(payload["results"])
        self.assertIn("applications", payload["related"])


if __name__ == "__main__":
    unittest.main()
