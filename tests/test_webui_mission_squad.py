from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WebUIMissionSquadTests(unittest.TestCase):
    def test_settings_exposes_aivy_team_summary(self):
        html = (ROOT / "webui" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "webui" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="squadSummary"', html)
        self.assertIn("async function loadSquadSummary()", app)
        self.assertIn("'/api/v1/agents'", app)

    def test_mission_buttons_bind_to_all_cards(self):
        app = (ROOT / "webui" / "app.js").read_text(encoding="utf-8")
        self.assertIn("$$('.mission-run').forEach", app)
        self.assertIn("$$('.mission-pause').forEach", app)
        self.assertIn("$$('.mission-cancel').forEach", app)
        self.assertNotIn("$(' .mission-run').forEach", app)

    def test_mission_cards_show_persisted_squad(self):
        app = (ROOT / "webui" / "app.js").read_text(encoding="utf-8")
        self.assertIn("mission-team", app)
        self.assertIn("(m.plan||{}).squad", app)

    def test_task_waves_and_release_guardian_are_visible(self):
        app = (ROOT / "webui" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Task Waves:", app)
        self.assertIn("runReleaseGuardian", app)
        self.assertIn("/release-guardian", app)


if __name__ == "__main__":
    unittest.main()
