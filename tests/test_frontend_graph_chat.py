from __future__ import annotations

import unittest
from pathlib import Path


class FrontendGraphChatTests(unittest.TestCase):
    def test_chat_drawer_hides_provisional_metadata_in_technical_details(self):
        source = Path("web/assets/modules/chat-drawer.js").read_text(encoding="utf-8")
        self.assertIn("source_type === \"llm_inferred\"", source)
        self.assertIn("assertion_kind === \"LLM_INFERRED\"", source)
        self.assertIn("validation_status === \"pending\"", source)
        self.assertIn("data-copy-edge", source)
        self.assertIn("graph-chat-technical-details", source)
        self.assertIn("Needs validation", source)
        index = Path("web/index.html").read_text(encoding="utf-8")
        self.assertIn("graph-chat-requirements-disclosure", index)
        self.assertIn("Set decision requirements", index)
        self.assertIn("Ask PackGraph", index)
        self.assertIn("graph-chat-mode", source)
        self.assertIn("graph-chat-lock", source)
        self.assertIn("previewRequest", source)
        self.assertIn("REQUIREMENTS_KEY", source)
        self.assertIn("buildPayloadContext", source)
        self.assertIn("requirements_review", source)
        self.assertIn("Requirements saved", source)
        self.assertIn("graph-chat-lineage-warning", source)

    def test_graph_chat_controller_wires_backend_owned_routes(self):
        source = Path("web/assets/modules/graph-chat-controller.js").read_text(encoding="utf-8")
        self.assertIn("PackGraphGraphChatController", source)
        self.assertIn("/query/preview", source)
        self.assertIn("/query/ask", source)
        self.assertIn("/query/enrich", source)
        self.assertIn("/runtime/workflow-status", source)

    def test_split_feature_controllers_exist(self):
        source_intake = Path("web/assets/modules/source-intake-controller.js").read_text(encoding="utf-8")
        workbench = Path("web/assets/modules/workbench-controller.js").read_text(encoding="utf-8")
        app = Path("web/assets/app.js").read_text(encoding="utf-8")
        self.assertIn("PackGraphSourceIntake", source_intake)
        self.assertIn("/source-intake/upload", source_intake)
        self.assertIn("/source-intake/sources", source_intake)
        self.assertIn("Advanced diagnostics", source_intake)
        self.assertIn("Can now answer from this source", source_intake)
        self.assertIn("data-source-chat", source_intake)
        self.assertIn("PackGraphWorkbenchController", workbench)
        self.assertIn("PackGraphSourceIntake?.upload", workbench)
        self.assertIn("PackGraphGraphChatController?.init", app)
        self.assertIn("PackGraphWorkbenchController?.setupForms", app)

    def test_admin_and_developer_tools_are_collapsed_from_main_user_flow(self):
        index = Path("web/index.html").read_text(encoding="utf-8")
        styles = Path("web/assets/style.css").read_text(encoding="utf-8")
        self.assertIn("developer-tools-section", index)
        self.assertIn("<summary>Developer tools</summary>", index)
        self.assertIn("adk_architecture/", index)
        self.assertIn("Quick command or search", index)
        self.assertIn("Upload source", index)
        self.assertIn("JSON and PDF supported. Stored locally.", index)
        self.assertIn("Advanced parameters", index)
        self.assertIn(">Help</button>", index)
        self.assertIn(".developer-tools-section", styles)

    def test_subtle_ui_helpers_are_shared_and_visible(self):
        shared = Path("web/assets/modules/shared-ui.js").read_text(encoding="utf-8")
        app = Path("web/assets/app.js").read_text(encoding="utf-8")
        styles = Path("web/assets/style.css").read_text(encoding="utf-8")
        index = Path("web/index.html").read_text(encoding="utf-8")
        self.assertIn("toast(message", shared)
        self.assertIn("bindDisclosureMemory", shared)
        self.assertIn("initHelpMenu", shared)
        self.assertIn("recent-entities-strip", index)
        self.assertIn("renderRecentEntitiesStrip", app)
        self.assertIn("Last updated", app)
        self.assertIn("table-entity-link", styles)
        self.assertIn("toast-stack", styles)


if __name__ == "__main__":
    unittest.main()
