import tempfile
import unittest
from pathlib import Path

from src.core.project_health import ProjectHealthCheck


class FakeExecutor:
    def __init__(self, *, tests=True, design=True, security=True):
        self.values = {
            "tests.run": {"passed": tests},
            "design.review": {"review": {"passed": design}},
            "security.scan": {"security": {"passed": security}},
        }
        self.calls = []

    class Row:
        def __init__(self, name, result):
            self.name = name
            self.result = result
        def to_dict(self):
            return {
                "tool_name": self.name,
                "status": "executed",
                "evidence_stage": "validate",
                "approval_required": False,
                "result": self.result,
            }

    def execute(self, name, args, run_id):
        self.calls.append((name, args, run_id))
        return self.Row(name, self.values[name])


class ProjectHealthCheckTests(unittest.TestCase):
    def test_all_three_reviewed_checks_must_pass(self):
        executor = FakeExecutor()
        report = ProjectHealthCheck(executor).run("demo")
        self.assertEqual(report.status, "pass")
        self.assertEqual([x[0] for x in executor.calls], ["tests.run", "design.review", "security.scan"])
        self.assertTrue(all(x[2] == report.run_id for x in executor.calls))

    def test_postflight_can_share_build_run_id_and_persist_summary(self):
        executor = FakeExecutor()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = ProjectHealthCheck(executor).run("demo", run_id="build-run-1")
            path = ProjectHealthCheck.save(root, report)
            self.assertEqual(report.run_id, "build-run-1")
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn('"status": "pass"', text)
            self.assertNotIn('"result"', text)

    def test_security_failure_requires_attention(self):
        report = ProjectHealthCheck(FakeExecutor(security=False)).run("demo")
        self.assertEqual(report.status, "attention_required")
        self.assertFalse(report.security_passed)


if __name__ == "__main__":
    unittest.main()
