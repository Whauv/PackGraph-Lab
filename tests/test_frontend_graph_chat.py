from __future__ import annotations

import unittest
from pathlib import Path


class FrontendGraphChatTests(unittest.TestCase):
    def test_chat_drawer_renders_provisional_metadata(self):
        source = Path("web/assets/modules/chat-drawer.js").read_text(encoding="utf-8")
        self.assertIn("source_type === \"llm_inferred\"", source)
        self.assertIn("assertion_kind === \"LLM_INFERRED\"", source)
        self.assertIn("validation_status === \"pending\"", source)
        self.assertIn("data-copy-edge", source)
        self.assertIn("graph-chat-mode", source)
        self.assertIn("graph-chat-lock", source)
        self.assertIn("previewRequest", source)
        self.assertIn("graph-chat-lineage-warning", source)

    def test_graph_chat_controller_wires_backend_owned_routes(self):
        source = Path("web/assets/modules/graph-chat-controller.js").read_text(encoding="utf-8")
        self.assertIn("PackGraphGraphChatController", source)
        self.assertIn("/query/preview", source)
        self.assertIn("/query/ask", source)
        self.assertIn("/runtime/workflow-status", source)

    def test_split_feature_controllers_exist(self):
        source_intake = Path("web/assets/modules/source-intake-controller.js").read_text(encoding="utf-8")
        workbench = Path("web/assets/modules/workbench-controller.js").read_text(encoding="utf-8")
        app = Path("web/assets/app.js").read_text(encoding="utf-8")
        self.assertIn("PackGraphSourceIntake", source_intake)
        self.assertIn("/source-intake/upload", source_intake)
        self.assertIn("/source-intake/sources", source_intake)
        self.assertIn("PackGraphWorkbenchController", workbench)
        self.assertIn("PackGraphSourceIntake?.upload", workbench)
        self.assertIn("PackGraphGraphChatController?.init", app)
        self.assertIn("PackGraphWorkbenchController?.setupForms", app)


if __name__ == "__main__":
    unittest.main()
