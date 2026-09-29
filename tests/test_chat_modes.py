from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.chat_partner import ChatPartner
from src.core.development_memory import DevelopmentMemory


class ChatModeTests(unittest.TestCase):
    def test_explicit_web_mode_is_kept_even_with_generic_make_word(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            partner = ChatPartner(DevelopmentMemory(root / "memory.jsonl"))
            partner.handle(
                project,
                "美容室サイト",
                "salon-site",
                "美容室向けで綺麗な感じに作って",
                has_generated=False,
                preferred_mode="web",
            )
            state = partner.state(project)
            self.assertEqual(state["current_mode"], "web")
            self.assertIn("web", state["targets"])

    def test_modes_add_distinct_build_quality_guidance(self):
        partner = ChatPartner()
        base = {
            "goal": "作成",
            "usage_context": "利用者が使う",
            "targets": ["web"],
            "design_style": "modern",
            "features": [],
        }
        web = partner._compose({**base, "current_mode": "web"})
        automation = partner._compose({**base, "current_mode": "automation"})
        app = partner._compose({**base, "current_mode": "app"})
        self.assertIn("WEB MODE", web)
        self.assertIn("SEO", web)
        self.assertIn("AUTOMATION MODE", automation)
        self.assertIn("重複実行防止", automation)
        self.assertIn("APP MODE", app)
        self.assertIn("認証・権限", app)

    def test_explicit_build_confirmation_is_not_absorbed_as_chat(self):
        partner = ChatPartner()
        self.assertFalse(
            partner.is_conversation_only(
                "この内容で作る",
                has_generated=False,
            )
        )

    def test_project_question_is_conversation_not_build(self):
        partner = ChatPartner()
        self.assertTrue(
            partner.is_conversation_only(
                "今のアプリはどこまでできてる？",
                has_generated=True,
            )
        )
        self.assertFalse(
            partner.is_conversation_only(
                "さっきのボタンをもっと大きくして",
                has_generated=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
