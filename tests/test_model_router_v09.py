import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.llm_chat import AIChatEngine
from src.core.model_router import ModelRouter


class MultiProviderModelRouterTests(unittest.TestCase):
    def test_capability_route_can_use_non_default_provider(self):
        with tempfile.TemporaryDirectory() as td:
            settings = Path(td) / "settings.json"
            engine = AIChatEngine(settings)
            engine.configure("openai", "openai-default", "openai-key", remember_key=False)
            engine.configure_provider("gemini", "gemini-vision", "gemini-key", remember_key=False)
            engine.configure_route("vision", "gemini", "gemini-vision")

            route = ModelRouter(engine).route("visual")
            self.assertEqual(route.mode, "capability_route")
            self.assertEqual(route.provider, "gemini")
            self.assertEqual(route.model, "gemini-vision")
            self.assertEqual(route.capability, "vision")

    def test_unconfigured_capability_falls_back_to_default_provider(self):
        with tempfile.TemporaryDirectory() as td:
            engine = AIChatEngine(Path(td) / "settings.json")
            engine.configure("openai", "default-model", "openai-key", remember_key=False)
            route = ModelRouter(engine).route("coding")
            self.assertEqual(route.mode, "configured_provider")
            self.assertEqual(route.provider, "openai")
            self.assertEqual(route.model, "default-model")

    def test_route_without_key_falls_back_safely(self):
        with tempfile.TemporaryDirectory() as td:
            settings = Path(td) / "settings.json"
            engine = AIChatEngine(settings)
            engine.configure("openai", "default-model", "openai-key", remember_key=False)
            data = engine._read()
            data["ai_profiles"] = {
                **(data.get("ai_profiles") or {}),
                "gemini": {"model": "gemini-reasoning"},
            }
            data["ai_routes"] = {
                "reasoning": {"provider": "gemini", "model": "gemini-reasoning"},
            }
            engine._write(data)

            with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
                route = ModelRouter(engine).route("reasoning")
            self.assertEqual(route.provider, "openai")
            self.assertEqual(route.mode, "configured_provider")

    def test_route_can_be_removed_without_touching_default_model(self):
        with tempfile.TemporaryDirectory() as td:
            engine = AIChatEngine(Path(td) / "settings.json")
            engine.configure("openai", "default-model", "key", remember_key=False)
            engine.configure_route("coding", "openai", "code-model")
            self.assertIsNotNone(engine.route_config("coding"))
            engine.configure_route("coding", "none")
            self.assertIsNone(engine.route_config("coding"))
            self.assertEqual(engine.settings()["model"], "default-model")


if __name__ == "__main__":
    unittest.main()
