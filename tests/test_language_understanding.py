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

    def test_daily_backlog_phrase_routes_to_ivy_lab(self):
        row = self.engine.interpret("今日アイビー何する？バックログ見せて")
        self.assertEqual(row.mode, "ivy_lab")
        self.assertGreaterEqual(row.confidence, 0.8)

    def test_daily_evolution_phrase_routes_to_ivy_lab(self):
        row = self.engine.interpret("アイビーを毎日自動で進化させて")
        self.assertEqual(row.mode, "ivy_lab")
        self.assertGreaterEqual(row.confidence, 0.8)

    def test_app_crud_feature_does_not_trigger_live_deletion_gate(self):
        prompt = (
            "スマホとPCで使えるToDo管理Webアプリを作って。"
            "タスクの追加・編集・削除・完了切り替えができるようにして。"
            "デザインはシンプルで高級感のあるものにしてほしい。"
            "設計からコード生成、テスト、プレビューまで進めて。"
        )
        row = self.engine.interpret(prompt)
        self.assertEqual(row.mode, "app")
        self.assertFalse(row.dangerous)
        self.assertFalse(row.needs_confirmation)

    def test_explicit_delete_feature_is_not_a_delete_command(self):
        for prompt in (
            "メモアプリに削除ボタンを実装して",
            "ToDoアプリを作りたい。タスクの削除機能がほしい",
            "Webアプリのタスクを削除できるようにして",
            "さっきのアプリにタスク削除機能を追加して",
        ):
            with self.subTest(prompt=prompt):
                self.assertFalse(self.engine.interpret(prompt).needs_confirmation)

    def test_real_deletions_and_other_sensitive_operations_keep_gate(self):
        for prompt in (
            "既存の顧客データを削除して",
            "アプリを作って、実際の顧客データを削除して",
            "このアプリに削除ボタンを作って、今の本番DBを削除して",
            "アプリの本番DB削除機能を作って",
            "アプリで課金機能を作って",
            "アプリで秘密鍵の削除機能を作って",
        ):
            with self.subTest(prompt=prompt):
                row = self.engine.interpret(prompt)
                self.assertTrue(row.dangerous)
                self.assertTrue(row.needs_confirmation)

    def test_risky_corrected_instruction_requires_confirmation(self):
        row = self.engine.interpret("ファイやベースの本番DBを削除して")
        self.assertTrue(row.dangerous)
        self.assertTrue(row.needs_confirmation)


if __name__ == "__main__":
    unittest.main()
