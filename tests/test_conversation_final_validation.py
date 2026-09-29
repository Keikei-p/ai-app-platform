from __future__ import annotations

from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class FinalConversationValidation(unittest.TestCase):
    def test_chatgpt_like_conversation_contract(self):
        brain=(ROOT/"src"/"core"/"conversation_brain.py").read_text(encoding="utf-8")
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        llm=(ROOT/"src"/"core"/"llm_chat.py").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        self.assertIn("class ConversationBrain",brain)
        self.assertIn("continuity_digest",brain)
        self.assertIn("reply_resilient",service)
        self.assertIn("def _ollama_reply",llm)
        self.assertIn("showThinking",app)
        self.assertIn("decision.project_slug&&decision.action!=='chat'",app)

if __name__=="__main__":
    unittest.main()
