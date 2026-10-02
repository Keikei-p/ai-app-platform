from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FinalDailyEvolutionValidation(unittest.TestCase):
    def test_daily_evolution_runtime_contract(self):
        daily=(ROOT/"src"/"core"/"daily_evolution.py").read_text(encoding="utf-8")
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        api=(ROOT/"src"/"core"/"platform_api.py").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        html=(ROOT/"webui"/"index.html").read_text(encoding="utf-8")
        self.assertIn("class DailyEvolutionEngine",daily)
        self.assertIn("already_completed_today",daily)
        self.assertIn('"max_practice_tasks_per_day": 1',daily)
        self.assertIn("self.daily_evolution.start_background()",service)
        self.assertIn("/api/v1/daily-evolution/status",api)
        self.assertIn("/api/v1/daily-evolution/run",app)
        self.assertIn("DAILY EVOLUTION",html)


if __name__=="__main__":
    unittest.main()
