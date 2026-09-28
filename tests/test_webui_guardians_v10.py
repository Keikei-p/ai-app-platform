from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class WebUIGuardianTests(unittest.TestCase):
    def test_settings_show_health_and_benchmark(self):
        html=(ROOT/"webui"/"index.html").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        self.assertIn('id="healthSummary"', html)
        self.assertIn('id="benchmarkSummary"', html)
        self.assertIn("async function loadHealthSummary()", app)
        self.assertIn("async function loadBenchmarkSummary()", app)

    def test_project_inspector_shows_guardian_states(self):
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        for token in (
            "Aivy Guardians",
            "Regression:",
            "Requirements:",
            "Dependencies:",
            "Accessibility:",
            "Performance:",
            "Project Memory:",
        ):
            self.assertIn(token, app)

if __name__ == "__main__":
    unittest.main()
