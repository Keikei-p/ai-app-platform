from __future__ import annotations

import unittest

from src.core.conversation_brain import ConversationBrain


class ConversationBrainTests(unittest.TestCase):
    def setUp(self):
        self.brain = ConversationBrain()

    def test_app_capability_question_does_not_create_project(self):
        intent = self.brain.classify(
            "アプリって作れるの？",
            has_project=False,
            mode="app",
            history=[],
        )
        self.assertEqual(intent.kind, "chat")
        self.assertFalse(intent.should_create_project)

    def test_explicit_creation_request_creates_project(self):
        intent = self.brain.classify(
            "営業管理アプリを作りたい",
            has_project=False,
            mode="app",
            history=[],
        )
        self.assertEqual(intent.kind, "project_request")
        self.assertTrue(intent.should_create_project)

    def test_soft_japanese_request_is_understood_as_request(self):
        intent = self.brain.classify(
            "予約サイト作ってくれる？",
            has_project=False,
            mode="web",
            history=[],
        )
        self.assertEqual(intent.kind, "project_request")
        self.assertTrue(intent.should_create_project)

    def test_project_question_remains_conversation(self):
        intent = self.brain.classify(
            "今のアプリってどこまでできてる？",
            has_project=True,
            mode="app",
            history=[{"role": "user", "content": "営業アプリを作りたい"}],
        )
        self.assertEqual(intent.kind, "project_question")
        self.assertFalse(intent.should_create_project)

    def test_short_followup_keeps_context(self):
        intent = self.brain.classify(
            "それってどういうこと？",
            has_project=True,
            mode="chat",
            history=[{"role": "assistant", "content": "Security確認が必要です。"}],
        )
        self.assertEqual(intent.kind, "project_question")

    def test_continuity_digest_keeps_older_user_context(self):
        history = []
        for i in range(40):
            history.append({"role": "user", "content": f"要望{i}: スマホで使いたい"})
            history.append({"role": "assistant", "content": f"確認{i}"})
        digest = self.brain.continuity_digest(history)
        self.assertIn("Earlier user context:", digest)
        self.assertIn("Recent conversation:", digest)
        self.assertLessEqual(len(digest), 7000)

    def test_system_instruction_forbids_fake_execution_claims(self):
        prompt = self.brain.system_instruction(
            mode="chat",
            continuity="User: hello",
            project_context={},
            self_drive_context={"enabled": True},
        )
        self.assertIn("実行していない変更", prompt)
        self.assertIn("制作命令だと勝手に解釈しない", prompt)
        self.assertIn("conversation_continuity", prompt)


if __name__ == "__main__":
    unittest.main()
