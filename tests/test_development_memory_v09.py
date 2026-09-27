import tempfile
import unittest
from pathlib import Path

from src.core.development_memory import DevelopmentMemory
from src.core.agent_runtime import AgentOrchestrator


class DevelopmentMemoryV09Tests(unittest.TestCase):
    def test_verified_lessons_can_be_filtered(self):
        with tempfile.TemporaryDirectory() as td:
            memory = DevelopmentMemory(Path(td) / "memory.jsonl")
            memory.record(
                category="guess",
                input_text="SNS 投稿",
                lesson="unverified guess",
                verified=False,
            )
            memory.record(
                category="verified",
                input_text="SNS 投稿",
                lesson="verified queue retry lesson",
                verified=True,
                evidence_source="test",
            )
            rows = memory.lessons_for("SNS 投稿", verified_only=True)
            self.assertEqual(rows, ["verified queue retry lesson"])

    def test_memory_redacts_sensitive_text_before_persisting(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "memory.jsonl"
            memory = DevelopmentMemory(path)
            memory.record(
                category="verified",
                input_text="Authorization: Bearer sk-abcdefghijklmnopqrstuvwxyz123456",
                lesson="never persist Authorization: Bearer sk-abcdefghijklmnopqrstuvwxyz123456",
                verified=True,
                evidence_source="test",
            )
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", raw)

    def test_agent_context_only_uses_verified_lessons(self):
        with tempfile.TemporaryDirectory() as td:
            memory = DevelopmentMemory(Path(td) / "memory.jsonl")
            memory.record(category="x", input_text="予約 アプリ", lesson="bad guess", verified=False)
            memory.record(category="x", input_text="予約 アプリ", lesson="real lesson", verified=True)
            context = AgentOrchestrator(memory).context("予約 アプリ")
            self.assertIn("real lesson", context["lessons"])
            self.assertNotIn("bad guess", context["lessons"])


if __name__ == "__main__":
    unittest.main()
