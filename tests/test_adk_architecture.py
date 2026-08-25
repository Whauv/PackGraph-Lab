from __future__ import annotations

import asyncio
import os
import unittest

from fastapi.testclient import TestClient

os.environ.setdefault("PACKGRAPH_NEO4J_TEST_STUB", "true")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "packgraph123")
os.environ.setdefault("NEO4J_DATABASE", "neo4j")

from adk_architecture.api import app
from adk_architecture.tool_runtime import list_tool_names, run_function_tool


class ADKArchitectureTests(unittest.TestCase):
    def test_tool_catalog_contains_expected_tools(self):
        tool_names = list_tool_names()
        self.assertIn("health_summary", tool_names)
        self.assertIn("query_graph", tool_names)
        self.assertIn("create_review_candidate", tool_names)

    def test_function_tool_health_runs(self):
        payload = asyncio.run(run_function_tool("health_summary"))
        self.assertIn("service", payload)
        self.assertIn("backend", payload)

    def test_adk_api_health(self):
        client = TestClient(app)
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["meta"]["mode"], "google-adk")


if __name__ == "__main__":
    unittest.main()
