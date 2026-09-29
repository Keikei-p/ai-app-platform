from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FinalSelfDriveValidation(unittest.TestCase):
    def test_self_drive_runtime_contract(self):
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        drive=(ROOT/"src"/"core"/"self_drive.py").read_text(encoding="utf-8")
        api=(ROOT/"src"/"core"/"platform_api.py").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        self.assertIn("SelfDriveEngine",service)
        self.assertIn("approved_build=False",service)
        self.assertIn('"max_actions_per_cycle": 1',drive)
        self.assertIn("approval_bypass_allowed",drive)
        self.assertIn("/api/v1/self-drive/run",api)
        self.assertIn("document.querySelectorAll('[data-mode]')",app)

if __name__=="__main__":
    unittest.main()
