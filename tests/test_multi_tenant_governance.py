from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.core.runtime_db import build_runtime_db
from app.services.agent_review import ReviewCandidateStore
from app.services.auth_service import AuthService
from app.services.governance_service import GovernanceService
from app.services.lineage_service import LineageService


class MultiTenantGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.settings = Settings(
            packgraph_data_dir=root / "generated",
            packgraph_runtime_dir=root / "runtime",
            packgraph_staging_dir=root / "staging",
            private_data_dir=root / "private",
            json_ingest_dir=root / "private",
            runtime_db_path=root / "runtime" / "packgraph_runtime.db",
            project_memory_path=root / "staging" / "project_memory.json",
            review_candidates_path=root / "staging" / "agent_review_candidates.json",
            agent_audit_path=root / "runtime" / "agent_audit.jsonl",
            review_audit_path=root / "runtime" / "review_audit.jsonl",
            entity_resolution_audit_path=root / "runtime" / "entity_resolution_audit.jsonl",
            match_decision_cache_path=root / "runtime" / "match_decision_cache.json",
            observability_log_path=root / "runtime" / "app_events.jsonl",
            metrics_path=root / "runtime" / "metrics_snapshot.json",
            auth_secret="test-secret",
        )
        self.settings.packgraph_runtime_dir.mkdir(parents=True, exist_ok=True)
        self.settings.packgraph_staging_dir.mkdir(parents=True, exist_ok=True)
        self.settings.private_data_dir.mkdir(parents=True, exist_ok=True)
        self.settings.project_memory_path.write_text("{}", encoding="utf-8")
        self.settings.review_candidates_path.write_text("[]", encoding="utf-8")
        self.settings.match_decision_cache_path.write_text("{}", encoding="utf-8")
        self.db = build_runtime_db(self.settings)
        self.auth = AuthService(self.settings, self.db)
        self.auth.ensure_seed()
        self.governance = GovernanceService(self.settings, self.db)
        self.governance.ensure_seed()
        self.lineage = LineageService(self.settings, self.db, self.governance)
        self.review_store = ReviewCandidateStore(self.settings, self.db)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_seeded_organizations_are_available(self):
        orgs = self.auth.list_organizations()
        slugs = {org["slug"] for org in orgs}
        self.assertEqual(slugs, {"demo-org", "customer-a", "customer-b"})

    def test_workspaces_are_isolated_by_org(self):
        demo_user = self.auth.login("analyst@packgraph.local", "packgraph-demo")
        customer_user = self.auth.login("analyst@customer-a.packgraph.local", "packgraph-demo")
        self.auth.save_workspace(demo_user["user_id"], {"name": "Demo workspace", "filters": {}, "selected_material_ids": [], "active_tab": "overview"})
        self.auth.save_workspace(customer_user["user_id"], {"name": "Customer workspace", "filters": {}, "selected_material_ids": [], "active_tab": "overview"})
        demo_workspaces = self.auth.list_workspaces(demo_user["user_id"])
        customer_workspaces = self.auth.list_workspaces(customer_user["user_id"])
        self.assertEqual({item["name"] for item in demo_workspaces}, {"Demo workspace"})
        self.assertEqual({item["name"] for item in customer_workspaces}, {"Customer workspace"})

    def test_review_candidates_are_filtered_by_org(self):
        self.review_store.create("entity_resolution", "Demo review", {"left": "A"}, org_id="ORG-001")
        self.review_store.create("entity_resolution", "Customer review", {"left": "B"}, org_id="ORG-002")
        demo_candidates = self.review_store.list(org_id="ORG-001")
        customer_candidates = self.review_store.list(org_id="ORG-002")
        self.assertEqual(len(demo_candidates), 1)
        self.assertEqual(len(customer_candidates), 1)
        self.assertNotEqual(demo_candidates[0]["org_id"], customer_candidates[0]["org_id"])

    def test_governance_and_lineage_payloads_are_org_scoped(self):
        source = self.governance.register_source(
            org_id="ORG-001",
            source_type="document",
            source_family="uploaded-document",
            display_name="Demo declaration",
            connector_name="local-upload",
            parser_name="packgraph-local-ingest",
            parser_version="2.0",
            trust_score=0.81,
        )
        edge = self.lineage.record_lineage(
            org_id="ORG-001",
            source_id=source["source_id"],
            artifact_id="ART-TEST-001",
            entity_type="document",
            entity_id="DOC-001",
            field_name="issued_on",
            citation_span="Issued on 2026-07-20",
            field_confidence=0.94,
            metadata={"material_id": "MAT-001"},
        )
        payload = self.lineage.provenance_viewer_payload(
            org_id="ORG-001",
            source_id=source["source_id"],
            artifact_id="ART-TEST-001",
            extracted_fields=[{"field_name": "issued_on", "confidence": 0.94}],
            summary="Demo declaration summary",
            uploaded_at="2026-07-20T12:00:00+00:00",
        )
        self.assertEqual(edge["org_id"], "ORG-001")
        self.assertEqual(payload["source"]["source_id"], source["source_id"])
        self.assertIn("retention", payload)


if __name__ == "__main__":
    unittest.main()
