"""Regression for black console flashes during Aivy background build/test work."""
import ast
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from src.core.process_launch import quiet_process_options

ROOT = Path(__file__).resolve().parents[1]


class FakeStartupInfo:
    def __init__(self):
        self.dwFlags = 0
        self.wShowWindow = 12


class QuietProcessLaunchTests(unittest.TestCase):
    def test_linux_and_mac_keep_subprocess_defaults(self):
        self.assertEqual(quiet_process_options(platform="posix"), {})

    def test_windows_hides_child_console_and_preserves_subprocess(self):
        with patch.object(subprocess, "STARTUPINFO", FakeStartupInfo, create=True):
            with patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
                with patch.object(subprocess, "STARTF_USESHOWWINDOW", 1, create=True):
                    with patch.object(subprocess, "SW_HIDE", 0, create=True):
                        options = quiet_process_options(platform="nt")
        self.assertEqual(options["creationflags"], 0x08000000)
        info = options["startupinfo"]
        self.assertEqual(info.dwFlags & 1, 1)
        self.assertEqual(info.wShowWindow, 0)

    def test_all_background_process_sites_use_hidden_startup(self):
        paths = {
            "test_runner.py": 1,
            "browser_capture.py": 1,
            "windows_packager.py": 2,
            "update_engine.py": 1,
            "ios_simulator_packager.py": 1,
            "android_packager.py": 1,
            "environment.py": 1,
        }
        for filename, count in paths.items():
            with self.subTest(filename=filename):
                source = (ROOT / "src" / "core" / filename).read_text(encoding="utf-8")
                tree = ast.parse(source)
                process_calls = [
                    node for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                    and node.func.attr == "run"
                ]
                self.assertEqual(len(process_calls), count)
                for call in process_calls:
                    self.assertTrue(
                        any(
                            kw.arg is None
                            and isinstance(kw.value, ast.Call)
                            and isinstance(kw.value.func, ast.Name)
                            and kw.value.func.id == "quiet_process_options"
                            for kw in call.keywords
                        ),
                        f"Missing quiet_process_options in {filename}",
                    )

    def test_background_acceptance_tools_hide_windows_child_console(self):
        # Acceptance scripts are sometimes run by Ivy's update verification.
        # Windows .cmd tools and child Python/Node processes must not flash.
        paths = {
            "acceptance_test.py": 2,
            "mobile_source_acceptance.py": 1,
            "remote_acceptance_test.py": 1,
            "windows_package_acceptance.py": 1,
        }
        for filename, count in paths.items():
            with self.subTest(filename=filename):
                source = (ROOT / "src" / "tools" / filename).read_text(
                    encoding="utf-8"
                )
                tree = ast.parse(source)
                calls = [
                    node for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "subprocess"
                    and node.func.attr == "run"
                ]
                self.assertEqual(len(calls), count)
                for call in calls:
                    self.assertTrue(
                        any(
                            kw.arg is None
                            and isinstance(kw.value, ast.Call)
                            and isinstance(kw.value.func, ast.Name)
                            and kw.value.func.id == "quiet_process_options"
                            for kw in call.keywords
                        ),
                        f"Missing quiet_process_options in {filename}",
                    )
                    self.assertTrue(any(
                        kw.arg == "shell"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value is False
                        for kw in call.keywords
                    ), f"Unexpected shell use in {filename}")

    def test_no_generic_powershell_or_unsafe_shell_introduced(self):
        for filename in ("test_runner.py", "browser_capture.py", "windows_packager.py",
                         "update_engine.py", "ios_simulator_packager.py", "android_packager.py",
                         "environment.py"):
            code = (ROOT / "src" / "core" / filename).read_text(encoding="utf-8")
            self.assertNotIn("shell=True", code)
            self.assertNotIn("powershell.exe", code.lower())


if __name__ == "__main__":
    unittest.main()
