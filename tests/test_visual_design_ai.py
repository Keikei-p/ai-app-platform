import base64
import json
import tempfile
import unittest
from pathlib import Path

from src.core.llm_chat import AIChatEngine
from src.core.visual_design_ai import VisualDesignAI


class FakeStatus:
    def __init__(self, connected=True, provider="openai", model="vision-model"):
        self.connected = connected
        self.provider = provider
        self.model = model


class FakeVisionEngine:
    def settings(self):
        return {"provider": "openai", "model": "vision-model"}

    def status(self):
        return FakeStatus()

    def vision_reply(self, image_paths, prompt, system):
        self.paths = list(image_paths)
        return json.dumps({
            "score": 94,
            "passed": True,
            "findings": ["desktop header could use slightly more spacing"],
            "strengths": ["responsive hierarchy is consistent"],
            "summary": "Strong responsive UI.",
        })


class OfflineVisionEngine(FakeVisionEngine):
    def status(self):
        return FakeStatus(False, "none", "")


class VisionInputTests(unittest.TestCase):
    def test_openai_vision_payload_uses_base64_data_url(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "screen.png"
            path.write_bytes(b"pngdata")
            engine = AIChatEngine()
            captured = {}

            def fake_request(url, headers, payload, timeout=60):
                captured.update({"url": url, "payload": payload})
                return {"output_text": "ok"}

            engine._request_json = fake_request
            result = engine._openai_vision_reply(
                "model", "key", engine._prepare_images([path]), "review", "system"
            )
            self.assertEqual(result, "ok")
            item = captured["payload"]["input"][0]["content"][1]
            self.assertEqual(item["type"], "input_image")
            self.assertTrue(item["image_url"].startswith("data:image/png;base64,"))
            self.assertEqual(base64.b64decode(item["image_url"].split(",", 1)[1]), b"pngdata")

    def test_gemini_vision_payload_uses_inline_data(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "screen.png"
            path.write_bytes(b"pngdata")
            engine = AIChatEngine()
            captured = {}

            def fake_request(url, headers, payload, timeout=60):
                captured.update({"url": url, "payload": payload})
                return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

            engine._request_json = fake_request
            result = engine._gemini_vision_reply(
                "model", "key", engine._prepare_images([path]), "review", "system"
            )
            self.assertEqual(result, "ok")
            part = captured["payload"]["contents"][0]["parts"][1]
            self.assertEqual(part["inlineData"]["mimeType"], "image/png")
            self.assertEqual(base64.b64decode(part["inlineData"]["data"]), b"pngdata")


class VisualDesignAITests(unittest.TestCase):
    def _screens(self, root: Path):
        folder = root / ".aiapp" / "screenshots"
        folder.mkdir(parents=True)
        for name in ("mobile.png", "tablet.png", "desktop.png"):
            (folder / name).write_bytes(b"image")

    def test_missing_screenshots_never_invent_visual_result(self):
        with tempfile.TemporaryDirectory() as td:
            review = VisualDesignAI(FakeVisionEngine()).review(Path(td))
            self.assertEqual(review.status, "screenshots_missing")
            self.assertIsNone(review.score)
            self.assertIsNone(review.passed)

    def test_disconnected_model_keeps_visual_review_pending(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._screens(root)
            review = VisualDesignAI(OfflineVisionEngine()).review(root)
            self.assertEqual(review.status, "model_not_connected")
            self.assertIsNone(review.score)

    def test_three_screenshots_are_actually_reviewed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._screens(root)
            engine = FakeVisionEngine()
            reviewer = VisualDesignAI(engine)
            review = reviewer.review(root)
            self.assertEqual(review.status, "reviewed")
            self.assertEqual(review.score, 94)
            self.assertTrue(review.passed)
            self.assertEqual(len(engine.paths), 3)
            path = reviewer.save(root, review)
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
