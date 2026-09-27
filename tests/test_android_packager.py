import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.android_packager import AndroidPackager
from src.core.app_spec import AppSpec


class AndroidPackagerTests(unittest.TestCase):
    def _spec(self):
        return AppSpec("Android Demo", "android-demo", "demo", "todo", [], ["android"])

    def _mobile(self, root: Path):
        mobile = root / "mobile"
        mobile.mkdir()
        (mobile / "package.json").write_text("{}", encoding="utf-8")
        (mobile / "node_modules").mkdir()
        return mobile

    def test_never_installs_missing_dependencies(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mobile = root / "mobile"
            mobile.mkdir()
            (mobile / "package.json").write_text("{}", encoding="utf-8")
            result = AndroidPackager(which=lambda name: "/bin/tool").build_debug_apk(root, self._spec())
            self.assertFalse(result.attempted)
            self.assertIn("will not install", result.detail)

    def test_fixed_prebuild_and_gradle_commands_create_debug_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            mobile = self._mobile(root)
            sdk = root / "sdk"
            sdk.mkdir()
            commands = []

            def runner(command, cwd, timeout):
                commands.append(command)
                if "prebuild" in command:
                    android = mobile / "android"
                    android.mkdir()
                    gradle = android / ("gradlew.bat" if os.name == "nt" else "gradlew")
                    gradle.write_text("", encoding="utf-8")
                else:
                    apk = mobile / "android/app/build/outputs/apk/debug/app-debug.apk"
                    apk.parent.mkdir(parents=True, exist_ok=True)
                    apk.write_bytes(b"apk")

            with patch.dict(os.environ, {"ANDROID_SDK_ROOT": str(sdk)}):
                result = AndroidPackager(
                    which=lambda name: f"/tools/{name}",
                    runner=runner,
                ).build_debug_apk(root, self._spec())

            self.assertTrue(result.attempted)
            self.assertTrue(result.built)
            self.assertTrue(result.artifact.is_file())
            self.assertTrue(str(result.artifact).endswith("android-demo-debug.apk"))
            self.assertEqual(len(commands), 2)
            self.assertEqual(commands[0][1:5], ["expo", "prebuild", "--platform", "android"])
            self.assertIn("assembleDebug", commands[1])
            self.assertFalse(any("install" in item for cmd in commands for item in cmd))

    def test_production_aab_is_not_part_of_debug_builder(self):
        source = Path(__file__).parents[1] / "src/core/android_packager.py"
        text = source.read_text(encoding="utf-8").lower()
        self.assertNotIn("bundleRelease".lower(), text)
        self.assertNotIn("publish", text)
        self.assertNotIn("store.submit", text)


if __name__ == "__main__":
    unittest.main()
