from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.llm_chat import AIChatEngine, ChatProviderStatus


class CloudFirstEngine(AIChatEngine):
    def __init__(self, path: Path):
        super().__init__(path)
        self.cloud_calls = 0
        self.local_calls = 0

    def status(self, provider=None, model=None):
        return ChatProviderStatus("openai", "test", True, "connected")

    def reply(self, history, user_text, system_instruction):
        self.cloud_calls += 1
        return "cloud reply"

    def _ollama_reply(self, model, history, user_text, system_instruction, *, base_url="http://127.0.0.1:11434"):
        self.local_calls += 1
        return "local reply"


class LocalFallbackEngine(AIChatEngine):
    def __init__(self, path: Path):
        super().__init__(path)
        self.local_calls = 0

    def status(self, provider=None, model=None):
        return ChatProviderStatus("none", "", False, "not connected")

    def _ollama_reply(self, model, history, user_text, system_instruction, *, base_url="http://127.0.0.1:11434"):
        self.local_calls += 1
        return "ollama reply"


class NoProviderEngine(LocalFallbackEngine):
    def _ollama_reply(self, model, history, user_text, system_instruction, *, base_url="http://127.0.0.1:11434"):
        raise RuntimeError("offline")


class ResilientConversationTests(unittest.TestCase):
    def test_cloud_provider_is_preferred(self):
        with TemporaryDirectory() as tmp:
            engine = CloudFirstEngine(Path(tmp) / "settings.json")
            reply = engine.reply_resilient([], "こんにちは", "system")
            self.assertEqual(reply, "cloud reply")
            self.assertEqual(engine.cloud_calls, 1)
            self.assertEqual(engine.local_calls, 0)

    def test_ollama_is_used_when_cloud_is_not_connected(self):
        with TemporaryDirectory() as tmp:
            engine = LocalFallbackEngine(Path(tmp) / "settings.json")
            reply = engine.reply_resilient([], "こんにちは", "system")
            self.assertEqual(reply, "ollama reply")
            self.assertEqual(engine.local_calls, 1)

    def test_unavailable_providers_raise_for_deterministic_fallback(self):
        with TemporaryDirectory() as tmp:
            engine = NoProviderEngine(Path(tmp) / "settings.json")
            with self.assertRaises(RuntimeError):
                engine.reply_resilient([], "こんにちは", "system")


if __name__ == "__main__":
    unittest.main()
