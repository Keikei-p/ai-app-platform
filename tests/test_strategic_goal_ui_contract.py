from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StrategicGoalUIContractTests(unittest.TestCase):
    def test_api_exposes_long_term_goal_controls(self):
        api=(ROOT/"src"/"core"/"platform_api.py").read_text(encoding="utf-8")
        self.assertIn('"/api/v1/strategic-goals"',api)
        self.assertIn('"/api/v1/strategic-goals/run"',api)
        self.assertIn('"pause"',api)
        self.assertIn('"resume"',api)
        self.assertIn('"cancel"',api)

    def test_platform_connects_strategy_to_daily_evolution(self):
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        self.assertIn("StrategicGoalStore",service)
        self.assertIn("StrategicAutonomyEngine",service)
        self.assertIn("strategy_cycle=",service)
        self.assertIn("strategy_status=",service)
        self.assertIn('"automatic_bounded_mission_generation": True',service)
        self.assertIn('"strategic_mission_approval_boundary": True',service)

    def test_mission_control_has_long_term_goal_ui(self):
        html=(ROOT/"webui"/"index.html").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        css=(ROOT/"webui"/"styles.css").read_text(encoding="utf-8")
        for token in (
            'id="strategicProject"',
            'id="strategicObjective"',
            'id="createStrategicGoal"',
            'id="runStrategicGoal"',
            'id="strategicGoalGrid"',
        ):
            self.assertIn(token,html)
        self.assertIn("/api/v1/strategic-goals",app)
        self.assertIn("async function createStrategicGoal()",app)
        self.assertIn("async function runStrategicGoal()",app)
        self.assertIn(".strategic-goal-card",css)

    def test_frequent_self_drive_no_longer_runs_deep_practice(self):
        drive=(ROOT/"src"/"core"/"self_drive.py").read_text(encoding="utf-8")
        self.assertNotIn('task_id="practice"',drive)
        self.assertNotIn('"practice_cooldown_seconds"',drive)
        self.assertIn('"practice_cadence": "daily_evolution_only"',drive)


if __name__=="__main__":
    unittest.main()
