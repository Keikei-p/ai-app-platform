import json
import tempfile
import unittest
from pathlib import Path

from src.core.evaluation_engine import EvaluationEngine


def write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class EvaluationEngineTests(unittest.TestCase):
    def test_verified_project_is_learning_eligible(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root / ".aiapp/reports/test_report.json", {
                "passed": True,
                "results": [{"name": "a", "passed": True}, {"name": "b", "passed": True}],
            })
            write(root / ".aiapp/reports/security_report.json", {"passed": True})
            write(root / ".aiapp/reports/build_readiness.json", {
                "preview_ready": True,
                "release_ready": True,
            })
            write(root / "design_review.json", {"passed": True, "score": 96})
            (root / "artifacts").mkdir()
            (root / "artifacts/app.zip").write_bytes(b"zip")
            report = EvaluationEngine().evaluate(root)
            self.assertTrue(report.learning_eligible)
            self.assertGreaterEqual(report.score, 95)
            self.assertEqual(report.artifact_count, 1)

    def test_security_failure_blocks_learning(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write(root / ".aiapp/reports/test_report.json", {
                "passed": True,
                "results": [{"name": "a", "passed": True}],
            })
            write(root / ".aiapp/reports/security_report.json", {"passed": False})
            write(root / ".aiapp/reports/build_readiness.json", {"preview_ready": False})
            write(root / "design_review.json", {"passed": True, "score": 95})
            report = EvaluationEngine().evaluate(root)
            self.assertFalse(report.learning_eligible)
            self.assertIn("security", report.regressions)

    def test_comparison_rejects_higher_score_with_critical_regression(self):
        engine = EvaluationEngine()
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            ar = Path(a); br = Path(b)
            for root, security, design in ((ar, True, 90), (br, False, 100)):
                write(root / ".aiapp/reports/test_report.json", {
                    "passed": True, "results": [{"name": "a", "passed": True}]
                })
                write(root / ".aiapp/reports/security_report.json", {"passed": security})
                write(root / ".aiapp/reports/build_readiness.json", {
                    "preview_ready": security, "release_ready": False
                })
                write(root / "design_review.json", {"passed": True, "score": design})
            before = engine.evaluate(ar)
            after = engine.evaluate(br)
            compared = engine.compare(before, after)
            self.assertTrue(compared["critical_regression"])
            self.assertFalse(compared["improved"])


if __name__ == "__main__":
    unittest.main()
