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
            'change.prepare': {'passed': True, 'checkpoint': {'checkpoint_id': 'fixture'}},
            "project.inspect": {"card": {"name": "Demo"}},
            "knowledge.search": {"knowledge": []},
            "tests.run": {"passed": tests, "results": []},
            "design.review": {"review": {"passed": design, "score": 95}},
            "security.scan": {"security": {"passed": security, "findings": []}},
            "package.build": {"status": "built", "external_release_performed": False},
        }

    def executable_tools(self):
        return ("project.inspect", "knowledge.search", "change.prepare", "tests.run", "design.review", "security.scan", "package.build")

    class Row:
        def __init__(self, result):
            self.result = result

    def execute(self, name, args, approved=False, run_id=""):
        self.calls.append((name, dict(args), approved, run_id))
        return self.Row(self.values[name])


class AgentPlanRunnerTests(unittest.TestCase):
    def test_preflight_executes_only_inspection_and_verified_knowledge(self):
        plan = AgentOrchestrator().plan("既存アプリを安全に改善する", "demo")
        executor = FakeExecutor()
        with tempfile.TemporaryDirectory() as td:
            report = AgentPlanRunner(executor).run_preflight(
                plan,
                project_dir=Path(td),
            )
        self.assertEqual(report.status, "completed")
        self.assertEqual(
            list(report.executed_tools),
            ["project.inspect", "knowledge.search", "change.prepare"],
        )
        called = [x[0] for x in executor.calls]
        self.assertEqual(called, ["project.inspect", "knowledge.search", "change.prepare"])
        self.assertNotIn("code.generate", called)
        self.assertNotIn("tests.run", called)
        self.assertNotIn("release.publish", called)

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
        self.assertIn("package.build", report.executed_tools)
        package_call = next(x for x in executor.calls if x[0] == "package.build")
        self.assertEqual(package_call[1]["project_slug"], "demo")
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


    def test_run_history_persists_only_redacted_summary_not_tool_results(self):
        plan = AgentOrchestrator().plan("password=super-secret-value を確認する", "demo")
        executor = FakeExecutor()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            report = AgentPlanRunner(executor).run(plan, project_dir=root)
            self.assertTrue(report.history_path)
            path = root / report.history_path
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("super-secret-value", text)
            self.assertNotIn('"result"', text)
            self.assertIn("[REDACTED]", text)

if __name__ == "__main__":
    unittest.main()
