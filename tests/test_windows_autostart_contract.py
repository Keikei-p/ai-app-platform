from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WindowsAutostartContractTests(unittest.TestCase):
    """Static safety checks only; NOT evidence of a real Windows reboot."""

    def test_opt_in_launcher_uses_current_install_and_known_fallback(self):
        silent = (ROOT / "AIVY_WEB_SILENT.vbs").read_text(encoding="utf-8")
        self.assertIn("WScript.ScriptFullName", silent)
        self.assertIn("AI-App-Platform-Git", silent)
        self.assertIn('call AIVY.bat web', silent)
        self.assertIn("IsAivyRunning", silent)

    def test_install_does_not_silently_register_autostart(self):
        enabled = (ROOT / "ENABLE_AIVY_AUTOSTART.vbs").read_text(encoding="utf-8")
        self.assertIn("Startup", enabled)
        self.assertIn("CreateShortcut", enabled)
        self.assertIn("AIVY_WEB_SILENT.vbs", enabled)
        self.assertIn("StrComp(link.TargetPath", enabled)
        self.assertIn("fso.FileExists(linkPath)", enabled)
        for base in ("AIVY.bat", "SETUP.bat", "INSTALL_OR_UPDATE.bat"):
            script = (ROOT / base).read_text(encoding="utf-8")
            self.assertNotIn("ENABLE_AIVY_AUTOSTART", script)
            self.assertNotIn("Ivy Web Autostart.lnk", script)

    def test_disable_only_removes_matching_shortcut(self):
        disabled = (ROOT / "DISABLE_AIVY_AUTOSTART.vbs").read_text(encoding="utf-8")
        self.assertIn("StrComp(link.TargetPath", disabled)
        self.assertIn("StrComp(link.Arguments", disabled)
        self.assertIn("fso.DeleteFile linkPath", disabled)
        self.assertNotIn("DeleteFolder", disabled)

    def test_release_checklist_requires_real_evidence(self):
        checklist = (ROOT / "docs" / "WINDOWS_STARTUP_RECOVERY.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("24 **real**", checklist)
        self.assertIn("No builds are automatically retried", checklist)
        self.assertIn("real Windows sign-in/reboot trial", checklist)


if __name__ == "__main__":
    unittest.main()
