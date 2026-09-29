from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ConversationUIContractTests(unittest.TestCase):
    def test_chat_ui_shows_thinking_and_copy_controls(self):
        app = (ROOT / "webui" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "webui" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("function showThinking()", app)
        self.assertIn("function removeThinking()", app)
        self.assertIn("navigator.clipboard.writeText", app)
        self.assertIn("Aivyが考えています", app)
        self.assertIn(".message.thinking", css)
        self.assertIn(".message-actions", css)

    def test_chat_action_does_not_open_build_plan(self):
        app = (ROOT / "webui" / "app.js").read_text(encoding="utf-8")
        self.assertIn("decision.project_slug&&decision.action!=='chat'", app)

    def test_platform_uses_conversation_brain_and_long_context(self):
        service = (ROOT / "src" / "core" / "platform_service.py").read_text(encoding="utf-8")
        brain = (ROOT / "src" / "core" / "conversation_brain.py").read_text(encoding="utf-8")
        self.assertIn("ConversationBrain", service)
        self.assertIn("continuity_digest", service)
        self.assertIn("conversation_intent_routing", service)
        self.assertIn("long_conversation_continuity", service)
        self.assertIn("質問や相談を、制作命令だと勝手に解釈しない", brain)


if __name__ == "__main__":
    unittest.main()
