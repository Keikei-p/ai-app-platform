import json
import tempfile
import unittest
from pathlib import Path

from src.core.browser_capture import BrowserScreenshotCapture
from src.core.preview_runtime import PreviewSession


class FakePreview:
    def __init__(self, root: Path, url="http://127.0.0.1:12345/"):
        self.root = root
        self.url = url
        self.started = False
        self.stopped = False

    def start(self, project_dir):
        self.started = True
        return PreviewSession(self.url, Path(project_dir))

    def stop(self):
        self.stopped = True


class BrowserScreenshotCaptureTests(unittest.TestCase):
    def _ready(self, root: Path, ready=True):
        path = root / ".aiapp" / "reports" / "build_readiness.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"preview_ready": ready, "blocking_reasons": []}), encoding="utf-8")

    def test_capture_is_blocked_before_quality_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._ready(root, False)
            browser = root / "chrome.exe"
            browser.write_bytes(b"x")
            with self.assertRaises(PermissionError):
                BrowserScreenshotCapture(
                    browser_path=browser,
                    preview=FakePreview(root),
                    runner=lambda command, timeout: None,
                ).capture(root)

    def test_only_loopback_preview_can_be_captured(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._ready(root)
            browser = root / "chrome.exe"
            browser.write_bytes(b"x")
            with self.assertRaises(PermissionError):
                BrowserScreenshotCapture(
                    browser_path=browser,
                    preview=FakePreview(root, "https://example.com/"),
                    runner=lambda command, timeout: None,
                ).capture(root)

    def test_three_fixed_viewports_are_captured(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._ready(root)
            browser = root / "chrome.exe"
            browser.write_bytes(b"x")
            commands = []

            def runner(command, timeout):
                commands.append(command)
                target = next(x.split("=", 1)[1] for x in command if x.startswith("--screenshot="))
                Path(target).write_bytes(b"png")

            preview = FakePreview(root)
            result = BrowserScreenshotCapture(
                browser_path=browser,
                preview=preview,
                runner=runner,
            ).capture(root)

            self.assertEqual(result.status, "captured")
            self.assertEqual(result.screenshots, ("mobile.png", "tablet.png", "desktop.png"))
            self.assertEqual(len(commands), 3)
            self.assertTrue(all(command[-1].startswith("http://127.0.0.1:") for command in commands))
            self.assertTrue(all("--headless=new" in command for command in commands))
            self.assertTrue(preview.stopped)


if __name__ == "__main__":
    unittest.main()
