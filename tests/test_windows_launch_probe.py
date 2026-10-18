"""Regression for Ivy startup/process-probe windows on Windows."""
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from src.core import environment


ROOT = Path(__file__).resolve().parents[1]


class WindowsLaunchProbeTests(unittest.TestCase):
    def test_environment_probe_hides_child_console_and_never_invokes_shell(self):
        with patch.object(environment.shutil, "which", return_value=r"C:\\Tools\\node.exe"):
            with patch.object(environment, "quiet_process_options", return_value={
                "creationflags": 0x08000000,
            }):
                with patch.object(environment.subprocess, "run", return_value=(
                    subprocess.CompletedProcess(["node", "--version"], 0, stdout="v24")
                )) as run:
                    self.assertEqual(environment._version("node"), "v24")
                    run.assert_called_once_with(
                        ["node", "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                        shell=False,
                        creationflags=0x08000000,
                    )

    def test_environment_probe_handles_missing_tool_without_launching(self):
        with patch.object(environment.shutil, "which", return_value=None):
            with patch.object(environment.subprocess, "run") as run:
                self.assertEqual(environment._version("npm"), "未検出")
                run.assert_not_called()

    def test_web_silent_uses_lightweight_healthcheck_not_status(self):
        script = (ROOT / "AIVY_WEB_SILENT.vbs").read_text(encoding="utf-8")
        self.assertIn('IsAivyRunning(url & "healthz")', script)
        self.assertNotIn('IsAivyRunning(url & "api/v1/status")', script)
        self.assertIn('InStr(1, http.ResponseText, """service"""', script)
        self.assertIn('InStr(1, http.ResponseText, """aivy"""', script)
        self.assertIn("cmd.exe /d /c", script)
        self.assertIn("shell.Run command, 0, False", script)

    def test_healthcheck_does_not_depend_on_model_or_project_status(self):
        source = (ROOT / "src/core/platform_api.py").read_text(encoding="utf-8")
        self.assertIn('if path in {"/healthz", "/api/v1/healthz"}:', source)
        self.assertIn('"service": "aivy"', source)
        self.assertIn('"status": "ok"', source)


if __name__ == "__main__":
    unittest.main()
