import tempfile
import unittest
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.chat_partner import ChatPartner
from src.core.design_ai import DesignAI
from src.core.generator import StarterGenerator
from src.core.social_generator import SocialAutomationGenerator


class V080DesignSystemTests(unittest.TestCase):
    def test_generated_app_has_modern_feedback_and_theme_controls(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec = AppSpec(
                "Salon Demo",
                "salon-demo",
                "美容サロンの予約管理",
                "booking",
                [],
                ["web"],
                design_style="soft",
                usage_context="スタッフがスマホで予約を確認する",
            )
            StarterGenerator().generate_from_spec(root, spec)
            html = (root / "index.html").read_text(encoding="utf-8")
            css = (root / "styles.css").read_text(encoding="utf-8")
            js = (root / "app.js").read_text(encoding="utf-8")
            self.assertIn('data-theme="soft"', html)
            self.assertIn('id="themeToggle"', html)
            self.assertIn('class="toast"', html)
            self.assertIn('id="confirmDialog"', html)
            self.assertIn("prefers-color-scheme", css)
            self.assertIn("confirmAction", js)
            review = DesignAI().review(root)
            self.assertTrue(review.passed, review.findings)
            self.assertGreaterEqual(review.score, 90)

    def test_theme_inference_handles_domain_and_social_context(self):
        generator = StarterGenerator()
        finance = AppSpec(
            "Money",
            "money",
            "資産管理をする金融アプリ",
            "dashboard",
            [],
            ["web"],
            design_style="custom",
        )
        social = AppSpec(
            "Social",
            "social",
            "SNS管理",
            "social_automation",
            ["social_publish"],
            ["web"],
            design_style="modern",
        )
        self.assertEqual(generator._resolve_theme(finance), "finance")
        self.assertEqual(generator._resolve_theme(social), "youthful")

    def test_natural_language_style_detection_is_expanded(self):
        partner = ChatPartner()
        state = {"targets": [], "features": []}
        partner._extract(state, "女性向けで柔らかい美容アプリにしたい")
        self.assertEqual(state.get("design_style"), "soft")
        state = {"targets": [], "features": []}
        partner._extract(state, "黒基調のダークモードで未来的に")
        self.assertIn(state.get("design_style"), {"future", "dark"})

    def test_social_generator_keeps_v080_design_quality(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec = AppSpec(
                "SNS Studio",
                "sns-studio",
                "ThreadsとYouTubeの予約投稿",
                "social_automation",
                ["scheduler", "social_publish"],
                ["web"],
                design_style="modern",
            )
            StarterGenerator().generate_from_spec(root, spec)
            SocialAutomationGenerator().generate(root, spec)
            html = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn('data-theme="youthful"', html)
            self.assertIn('id="themeToggle"', html)
            self.assertIn('id="confirmDialog"', html)
            review = DesignAI().review(root)
            self.assertTrue(review.passed, review.findings)


if __name__ == "__main__":
    unittest.main()
