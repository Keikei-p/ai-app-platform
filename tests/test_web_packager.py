import json
import tempfile
import unittest
import zipfile
from hashlib import sha256
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.web_packager import WebPackager


class WebPackagerTests(unittest.TestCase):
    def _spec(self):
        return AppSpec("Demo", "demo", "web app", "todo", [], ["web"])

    def test_build_creates_zip_and_checksum_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text("<title>Demo</title>", encoding="utf-8")
            (root / "app.js").write_text("console.log('ok')", encoding="utf-8")
            result = WebPackager().build(root, self._spec())
            self.assertTrue(result.built)
            self.assertTrue(result.artifact.is_file())
            self.assertTrue(result.manifest.is_file())
            manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest["sha256"], sha256(result.artifact.read_bytes()).hexdigest())
            with zipfile.ZipFile(result.artifact) as archive:
                self.assertIn("index.html", archive.namelist())
                self.assertIn("app.js", archive.namelist())

    def test_runtime_and_secret_files_are_not_packaged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "index.html").write_text("<title>Demo</title>", encoding="utf-8")
            (root / "app_data.db").write_bytes(b"private")
            (root / ".env").write_text("SECRET=x", encoding="utf-8")
            (root / ".aiapp" / "reports").mkdir(parents=True)
            (root / ".aiapp" / "reports" / "secret.json").write_text("{}", encoding="utf-8")
            result = WebPackager().build(root, self._spec())
            with zipfile.ZipFile(result.artifact) as archive:
                names = archive.namelist()
                self.assertNotIn("app_data.db", names)
                self.assertNotIn(".env", names)
                self.assertFalse(any(name.startswith(".aiapp/") for name in names))

    def test_non_web_target_does_not_build(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec = AppSpec("Demo", "demo", "mobile", "todo", [], ["android"])
            result = WebPackager().build(root, spec)
            self.assertFalse(result.built)
            self.assertIsNone(result.artifact)


if __name__ == "__main__":
    unittest.main()
