from __future__ import annotations
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class FinalStrategicAutonomyValidationV2(unittest.TestCase):
    def test_final_long_term_autonomy_contract(self):
        strategy=(ROOT/"src"/"core"/"strategic_goals.py").read_text(encoding="utf-8")
        daily=(ROOT/"src"/"core"/"daily_evolution.py").read_text(encoding="utf-8")
        drive=(ROOT/"src"/"core"/"self_drive.py").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        self.assertIn("StrategicAutonomyEngine",strategy)
        self.assertIn("waiting_on_mission",strategy)
        self.assertIn("strategy_cycle",daily)
        self.assertNotIn('task_id="practice"',drive)
        self.assertIn("document.querySelectorAll('.mission-run').forEach",app)

if __name__=="__main__":
    unittest.main()
