"""Fast interactive startup and duplicate Windows GUI prevention."""
from __future__ import annotations

import os
from pathlib import Path
import unittest

from src.core.desktop_instance import desktop_instance_lock

ROOT = Path(__file__).resolve().parents[1]


class FastDesktopStartupTests(unittest.TestCase):
    def test_normal_startup_does_not_run_full_suite_before_showing_chat(self):
        start = (ROOT / "START.bat").read_text(encoding="utf-8").lower()
        full = (ROOT / "CHECK.bat").read_text(encoding="utf-8").lower()
        self.assertIn("src.tools.preflight", start)
        self.assertIn("src.main", start)
        self.assertNotIn("-m unittest discover", start)
        self.assertIn("-m unittest discover", full)

    def test_gui_entry_point_protects_main_window_with_mutex(self):
        source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        self.assertIn("with desktop_instance_lock() as can_start:", source)
        self.assertIn("if not can_start:", source)
        self.assertIn("MainWindow().mainloop()", source)
        self.assertNotIn("os.system(", source)

    @unittest.skipUnless(os.name == "nt", "Windows mutex requires Windows")
    def test_real_windows_mutex_rejects_second_gui_and_recovers(self):
        with desktop_instance_lock() as first:
            self.assertTrue(first)
            with desktop_instance_lock() as second:
                self.assertFalse(second)
        with desktop_instance_lock() as third:
            self.assertTrue(third)

    def test_silent_desktop_shortcut_does_not_create_powershell_window(self):
        script = (ROOT / "AIVY_DESKTOP_SILENT.vbs").read_text(encoding="utf-8").lower()
        self.assertIn("shell.run(command, 0, true)", script)
        self.assertIn("call aivy.bat", script)
        self.assertIn('shell.appactivate("ai app platform v")', script)
        self.assertIn("cmd.exe /d /c", script)
        self.assertNotIn("powershell", script)
        self.assertNotIn("enable_aivy_autostart", script)

    def test_no_destructive_update_or_hidden_build_approval(self):
        for path in ("AIVY_DESKTOP_SILENT.vbs", "START.bat", "src/core/desktop_instance.py"):
            source = (ROOT / path).read_text(encoding="utf-8").lower()
            for forbidden in ("reset --hard", "clean -fd", "taskkill", "rmdir /s",
                              "force=true", "production_deploy"):
                self.assertNotIn(forbidden, source, path)


if __name__ == "__main__":
    unittest.main()
