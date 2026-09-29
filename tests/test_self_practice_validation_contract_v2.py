from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FinalSelfPracticeValidation(unittest.TestCase):
    def test_final_develop_self_practice_contract(self):
        service = (ROOT / "src" / "core" / "platform_service.py").read_text(encoding="utf-8")
        practice = (ROOT / "src" / "core" / "self_practice.py").read_text(encoding="utf-8")
        growth = (ROOT / "src" / "core" / "autonomous_growth.py").read_text(encoding="utf-8")
        app = (ROOT / "webui" / "app.js").read_text(encoding="utf-8")
        self.assertIn("SelfPracticeEngine", service)
        self.assertIn("set_practice_runner", service)
        self.assertIn("CandidateArena", practice)
        self.assertIn("dimension_review", practice)
        self.assertIn("practice_queue_clear", practice)
        self.assertIn("production_data_used", practice)
        self.assertIn("if int(score) < 90", growth)
        self.assertIn("/api/v1/practice/run", app)


if __name__ == "__main__":
    unittest.main()
