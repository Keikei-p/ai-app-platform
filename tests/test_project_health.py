import unittest

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

    def test_security_failure_requires_attention(self):
        report = ProjectHealthCheck(FakeExecutor(security=False)).run("demo")
        self.assertEqual(report.status, "attention_required")
        self.assertFalse(report.security_passed)


if __name__ == "__main__":
    unittest.main()
