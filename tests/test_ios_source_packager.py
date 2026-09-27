import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.ios_source_packager import IOSSourcePackager


class IOSSourcePackagerTests(unittest.TestCase):
    def _spec(self):
        return AppSpec("iOS Demo", "ios-demo", "demo", "todo", [], ["ios"])

    def _mobile(self, root: Path):
        mobile = root / "mobile"
        mobile.mkdir()
        for name, value in {
            "package.json": "{}",
            "app.json": "{}",
            "eas.json": "{}",
            "tsconfig.json": "{}",
            "App.tsx": "export default function App(){}",
            "README.md": "# demo",
        }.items():
            (mobile / name).write_text(value, encoding="utf-8")
        return mobile

    def test_builds_source_zip_with_checksum_but_not_ipa(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._mobile(root)
            result = IOSSourcePackager().build(root, self._spec())
            self.assertTrue(result.built)
            self.assertTrue(result.artifact.is_file())
            self.assertTrue(result.manifest.is_file())
            self.assertTrue(result.artifact.name.endswith("-ios-source.zip"))
            self.assertFalse(any(root.rglob("*.ipa")))
            manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
            self.assertFalse(manifest["signed_ipa"])
            self.assertEqual(manifest["sha256"], result.sha256)

    def test_excludes_dependencies_secrets_and_native_build_directories(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mobile = self._mobile(root)
            (mobile / ".env").write_text("SECRET=value", encoding="utf-8")
            (mobile / "credentials.json").write_text("secret", encoding="utf-8")
            (mobile / "node_modules").mkdir()
            (mobile / "node_modules/secret.txt").write_text("x", encoding="utf-8")
            result = IOSSourcePackager().build(root, self._spec())
            with zipfile.ZipFile(result.artifact) as archive:
                names = archive.namelist()
            self.assertNotIn("mobile/.env", names)
            self.assertNotIn("mobile/credentials.json", names)
            self.assertFalse(any("node_modules" in x for x in names))

    def test_missing_mobile_source_does_not_create_fake_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = IOSSourcePackager().build(root, self._spec())
            self.assertFalse(result.built)
            self.assertIsNone(result.artifact)


if __name__ == "__main__":
    unittest.main()
