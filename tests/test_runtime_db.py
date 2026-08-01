from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.config import Settings
from app.core.runtime_db import build_runtime_db


class RuntimeDatabaseTests(unittest.TestCase):
    def test_migrations_create_runtime_tables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = Settings(
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
            )
            settings.packgraph_runtime_dir.mkdir(parents=True, exist_ok=True)
            settings.packgraph_staging_dir.mkdir(parents=True, exist_ok=True)
            settings.project_memory_path.write_text("{}", encoding="utf-8")
            settings.review_candidates_path.write_text("[]", encoding="utf-8")
            settings.match_decision_cache_path.write_text("{}", encoding="utf-8")
            db = build_runtime_db(settings)
            health = db.health()
            self.assertGreaterEqual(health["migrations"], 2)
            with db.connect() as connection:
                source_registry = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='source_registry'").fetchone()
                lineage_edges = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lineage_edges'").fetchone()
            self.assertIsNotNone(source_registry)
            self.assertIsNotNone(lineage_edges)


if __name__ == "__main__":
    unittest.main()
