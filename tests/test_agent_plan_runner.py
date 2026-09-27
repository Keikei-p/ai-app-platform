import unittest
from pathlib import Path
import tempfile

from src.core.agent_plan_runner import AgentPlanRunner
from src.core.agent_runtime import AgentOrchestrator


class FakeExecutor:
    def __init__(self, *, tests=True, design=True, security=True):
        self.registry = AgentOrchestrator().tools
        self.calls = []
        self.values = {
            "project.inspect": {"card": {"name": "Demo"}},
            "knowledge.search": {"knowledge": []},
            "tests.run": {"passed": tests, "results": []},
            "design.review": {"review": {"passed": design, "score": 95}},
            "security.scan": {"security": {"passed": security, "findings": []}},
        }

    def executable_tools(self):
        return ("project.inspect", "knowledge.search", "tests.run", "design.review", "security.scan")

    class Row:
        def __init__(self, result):
            self.result = result

    def execute(self, name, args, approved=False, run_id=""):
        self.calls.append((name, dict(args), approved, run_id))
        return self.Row(self.values[name])


class AgentPlanRunnerTests(unittest.TestCase):
    def test_reviewed_tools_execute_and_unbound_tools_are_delegated(self):
        plan = AgentOrchestrator().plan("既存アプリを改善する", "demo")
        executor = FakeExecutor()
        with tempfile.TemporaryDirectory() as td:
            report = AgentPlanRunner(executor).run(plan, project_dir=Path(td))
        self.assertIn("project.inspect", report.executed_tools)
        self.assertIn("knowledge.search", report.executed_tools)
        self.assertIn("tests.run", report.executed_tools)
        self.assertIn("design.review", report.executed_tools)
        self.assertIn("security.scan", report.executed_tools)
        self.assertIn("code.generate", report.delegated_tools)
        self.assertEqual(report.status, "approval_required")
        self.assertIn("release.publish", report.approval_required)
        self.assertFalse(report.arbitrary_shell)

    def test_validation_failure_stops_before_release(self):
        plan = AgentOrchestrator().plan("壊れていないか確認する", "demo")
        executor = FakeExecutor(security=False)
        report = AgentPlanRunner(executor).run(plan)
        self.assertEqual(report.status, "blocked")
        self.assertIn("security.scan", report.executed_tools)
        self.assertNotIn("release.publish", report.approval_required)

    def test_approval_does_not_make_unbound_release_executable(self):
        plan = AgentOrchestrator().plan("公開準備を確認する", "demo")
        executor = FakeExecutor()
        report = AgentPlanRunner(executor).run(
            plan,
            approved_tools={"release.publish"},
        )
        self.assertIn("release.publish", report.delegated_tools)
        self.assertNotIn("release.publish", report.executed_tools)

    def test_step_budget_is_enforced(self):
        plan = AgentOrchestrator().plan("test", "demo")
        plan.steps = plan.steps * 3
        with self.assertRaises(ValueError):
            AgentPlanRunner(FakeExecutor()).run(plan)


if __name__ == "__main__":
    unittest.main()
