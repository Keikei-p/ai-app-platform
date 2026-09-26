import json
import tempfile
import unittest
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.windows_packager import WindowsPackager


class WindowsPackagerTests(unittest.TestCase):
    def _spec(self):
        return AppSpec("Demo", "demo", "windows app", "todo", [], ["web", "windows"])

    def test_prepare_creates_payload_launcher_and_build_script(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text("<title>Demo</title>", encoding="utf-8")
            (root / "app.js").write_text("console.log('ok')", encoding="utf-8")
            result = WindowsPackager().prepare(root, self._spec())
            self.assertTrue(result.prepared)
            self.assertTrue((root / "windows" / "payload" / "index.html").is_file())
            self.assertTrue((root / "windows" / "launcher.py").is_file())
            self.assertTrue((root / "BUILD_GENERATED_WINDOWS.bat").is_file())
            manifest = json.loads((root / "windows" / "package_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifact"], "artifacts/windows/demo.exe")

    def test_runtime_database_is_not_bundled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text("<title>Demo</title>", encoding="utf-8")
            (root / "app_data.db").write_bytes(b"private runtime data")
            WindowsPackager().prepare(root, self._spec())
            self.assertFalse((root / "windows" / "payload" / "app_data.db").exists())

    def test_non_windows_target_does_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec = AppSpec("Demo", "demo", "web", "todo", [], ["web"])
            result = WindowsPackager().prepare(root, spec)
            self.assertFalse(result.prepared)
            self.assertFalse((root / "windows").exists())


if __name__ == "__main__":
    unittest.main()
