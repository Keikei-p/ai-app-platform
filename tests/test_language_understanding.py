from __future__ import annotations

import unittest

from src.core.language_understanding import LanguageUnderstandingEngine


class LanguageUnderstandingTests(unittest.TestCase):
    def setUp(self):
        self.engine = LanguageUnderstandingEngine()

    def test_common_japanese_service_typo_is_normalized(self):
        row = self.engine.interpret("ファイやベースでログイン作って")
        self.assertIn("Firebase", row.interpreted_text)
        self.assertEqual(row.mode, "app")
        self.assertTrue(row.corrections)

    def test_ascii_typo_is_fuzzy_corrected(self):
        row = self.engine.interpret("Githb に保存して")
        self.assertIn("GitHub", row.interpreted_text)
        self.assertTrue(any(x["kind"] == "fuzzy" for x in row.corrections))

    def test_web_site_request_routes_to_web_mode(self):
        row = self.engine.interpret("美容室のホームページを作りたい")
        self.assertEqual(row.mode, "web")

    def test_rough_japanese_input_is_normalized_without_losing_intent(self):
        row = self.engine.interpret("本番実装に知被けるようにやって、モーdも確認")
        self.assertIn("本番実装に近づけ", row.interpreted_text)
        self.assertIn("モード", row.interpreted_text)
        self.assertEqual(row.mode, "app")

    def test_reference_without_context_lowers_confidence(self):
        without_context = self.engine.interpret("さっきのボタンもっと大きくして")
        with_context = self.engine.interpret(
            "さっきのボタンもっと大きくして",
            {"project_slug": "demo", "recent_messages": [{"role": "user", "content": "button"}]},
        )
        self.assertLess(without_context.confidence, with_context.confidence)

    def test_plain_aivy_name_mention_stays_in_normal_chat(self):
        row = self.engine.interpret("アイビーって何ができるの？")
        self.assertEqual(row.mode, "chat")

    def test_self_drive_phrase_routes_to_ivy_lab(self):
        row = self.engine.interpret("よし自走してほしい")
        self.assertEqual(row.mode, "ivy_lab")
        self.assertGreaterEqual(row.confidence, 0.8)

    def test_risky_corrected_instruction_requires_confirmation(self):
        row = self.engine.interpret("ファイやベースの本番DBを削除して")
        self.assertTrue(row.dangerous)
        self.assertTrue(row.needs_confirmation)


if __name__ == "__main__":
    unittest.main()
