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


if __name__ == "__main__":
    unittest.main()
