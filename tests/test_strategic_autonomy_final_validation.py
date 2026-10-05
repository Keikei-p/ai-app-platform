from __future__ import annotations

from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class FinalStrategicAutonomyValidation(unittest.TestCase):
    def test_long_term_goal_loop_is_fully_wired(self):
        strategy=(ROOT/"src"/"core"/"strategic_goals.py").read_text(encoding="utf-8")
        daily=(ROOT/"src"/"core"/"daily_evolution.py").read_text(encoding="utf-8")
        drive=(ROOT/"src"/"core"/"self_drive.py").read_text(encoding="utf-8")
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        self.assertIn("class StrategicAutonomyEngine",strategy)
        self.assertIn('"build_auto_approved": False',strategy)
        self.assertIn("strategy_cycle",daily)
        self.assertNotIn('task_id="practice"',drive)
        self.assertIn("StrategicGoalStore",service)
        self.assertIn("/api/v1/strategic-goals",app)

if __name__=="__main__":
    unittest.main()
