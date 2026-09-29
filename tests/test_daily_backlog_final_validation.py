from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FinalDailyBacklogValidation(unittest.TestCase):
    def test_daily_backlog_is_connected_to_self_drive(self):
        backlog=(ROOT/"src"/"core"/"autonomous_backlog.py").read_text(encoding="utf-8")
        drive=(ROOT/"src"/"core"/"self_drive.py").read_text(encoding="utf-8")
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        api=(ROOT/"src"/"core"/"platform_api.py").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        self.assertIn("class AutonomousBacklog",backlog)
        self.assertIn("waiting_approval",backlog)
        self.assertIn("set_after_cycle",drive)
        self.assertIn("persistent_daily_backlog",service)
        self.assertIn("/api/v1/backlog/today",api)
        self.assertIn("async function refreshBacklog()",app)

if __name__=="__main__":
    unittest.main()
