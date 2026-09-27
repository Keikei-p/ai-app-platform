import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.core.app_spec import AppSpec
from src.core.coding_brain import CodingBrain


class FakeEngine:
    def __init__(self, reply_text: str, connected: bool = True):
        self.reply_text = reply_text
        self.connected = connected

    def status(self):
        return SimpleNamespace(connected=self.connected, detail="connected" if self.connected else "AIモデル未接続")

    def reply(self, history, user_text, system_instruction):
        return self.reply_text


class CodingBrainTests(unittest.TestCase):
    def _spec(self):
        return AppSpec("Demo", "demo", "todo app", "todo", [], ["web"])

    def test_unconnected_engine_falls_back_without_changes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            brain = CodingBrain(FakeEngine("", connected=False))
            result = brain.enhance(root, self._spec(), "make it better")
            self.assertEqual(result.status, "not_connected")
            self.assertEqual(result.files, [])

    def test_valid_json_proposal_is_applied(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text("old", encoding="utf-8")
            payload = '{"summary":"improved","files":[{"path":"index.html","content":"<title>New</title>"},{"path":"src/app.js","content":"console.log(1);"}]}'
            result = CodingBrain(FakeEngine(payload)).enhance(root, self._spec(), "improve")
            self.assertEqual(result.status, "applied")
            self.assertEqual((root / "index.html").read_text(encoding="utf-8"), "<title>New</title>")
            self.assertTrue((root / "src" / "app.js").is_file())

    def test_markdown_fenced_json_is_parsed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload = "```" + 'json\n{"summary":"ok","files":[{"path":"app.js","content":"const x = 1;"}]}\n' + "```"
            result = CodingBrain(FakeEngine(payload)).enhance(root, self._spec(), "improve")
            self.assertEqual(result.status, "applied")
            self.assertEqual((root / "app.js").read_text(encoding="utf-8"), "const x = 1;")

    def test_path_traversal_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload = '{"files":[{"path":"../escape.py","content":"print(1)"},{"path":"safe.js","content":"ok"}]}'
            with self.assertRaises(ValueError):
                CodingBrain(FakeEngine(payload)).enhance(root, self._spec(), "improve")
            self.assertFalse((root / "safe.js").exists())

    def test_platform_metadata_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payload = '{"files":[{"path":"app_spec.json","content":"{}"}]}'
            with self.assertRaises(ValueError):
                CodingBrain(FakeEngine(payload)).enhance(root, self._spec(), "improve")

    def test_env_and_binary_credentials_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for bad in [".env", "signing.p12", "private.key"]:
                payload = '{"files":[{"path":"' + bad + '","content":"secret"}]}'
                with self.assertRaises(ValueError):
                    CodingBrain(FakeEngine(payload)).enhance(root, self._spec(), "improve")


if __name__ == "__main__":
    unittest.main()
