"""Regression: Windows Script Host reads .vbs files as the system ANSI codepage.

Bare UTF-8 Japanese text can consume a closing quote on Japanese Windows and
raise Microsoft VBScript compilation error 800A0409 at startup. Windows CI
also compiles every script with cscript.exe under an opt-in safe exit.
"""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LAUNCHERS = (
    "AIVY_WEB_SILENT.vbs",
    "AIVY_DESKTOP_SILENT.vbs",
    "ENABLE_AIVY_AUTOSTART.vbs",
    "DISABLE_AIVY_AUTOSTART.vbs",
)


class WindowsVbscriptEncodingContractTests(unittest.TestCase):
    def test_launchers_are_ascii_only_for_windows_ansi_parser(self):
        for name in LAUNCHERS:
            with self.subTest(name=name):
                content = (ROOT / name).read_bytes()
                self.assertTrue(content, "Empty script")
                self.assertTrue(content.isascii(), f"{name}: non-ASCII source is unsafe for WSH")
                self.assertTrue(content.startswith(b"Option Explicit"))
                self.assertIn(b"%AIVY_VBS_SYNTAX_CHECK%", content)
                self.assertIn(b"WScript.Quit 0", content)

    def test_ci_invokes_real_windows_script_host_with_no_side_effects(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("AIVY_VBS_SYNTAX_CHECK", workflow)
        self.assertIn("cscript.exe", workflow)
        for name in LAUNCHERS:
            with self.subTest(name=name):
                self.assertIn(name, workflow)


if __name__ == "__main__":
    unittest.main()
