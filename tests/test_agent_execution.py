import unittest
from dataclasses import dataclass

from src.core.agent_budget import AgentBudget
from src.core.agent_execution import AgentExecutionLoop
from src.core.agent_tools import AgentToolRegistry
from src.core.specialist_agents import SpecialistAgentRegistry
from src.core.specialist_council import CouncilReport, CouncilTurn
from src.core.specialist_runtime import SpecialistResult


@dataclass
class FakeExecution:
    tool_name: str
    result: dict
    status: str = "executed"
    evidence_stage: str = "validate"
    approval_required: bool = False

    def to_dict(self):
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "evidence_stage": self.evidence_stage,
            "approval_required": self.approval_required,
            "result": self.result,
        }


class FakeExecutor:
    def __init__(self, executable=None):
        self.calls = []
        self._executable = tuple(executable or (
            "project.inspect", "knowledge.search", "tests.run",
            "design.review", "security.scan",
        ))

    def executable_tools(self):
        return self._executable

    def execute(self, tool_name, args, approved=False, run_id=""):
        self.calls.append((tool_name, dict(args), approved, run_id))
        return FakeExecution(tool_name, {"ok": True})


def result(name, requested):
    return SpecialistResult(
        specialist=name,
        status="ok",
        summary="ok",
        findings=(),
        recommendations=(),
        requested_tools=tuple(requested),
        uncertainties=(),
        route={},
    )


def report(turns):
    return CouncilReport(
        goal="improve secure app",
        status="ok",
        advisory_only=True,
        turns=tuple(CouncilTurn(i + 1, name, result(name, requested)) for i, (name, requested) in enumerate(turns)),
        requested_tools=tuple(x for _, names in turns for x in names),
        approval_required_tools=(),
        budget={},
        summary="ok",
    )


class AgentExecutionLoopTests(unittest.TestCase):
    def test_executes_only_role_allowed_reviewed_tools_with_derived_args(self):
        executor = FakeExecutor()
        loop = AgentExecutionLoop(executor=executor)
        council = report((
            ("research", ("knowledge.search",)),
            ("test", ("tests.run",)),
            ("security", ("security.scan",)),
        ))
        out = loop.run(council, project_slug="demo")
        self.assertEqual(out.status, "completed")
        self.assertEqual([x[0] for x in executor.calls], ["knowledge.search", "tests.run", "security.scan"])
        self.assertEqual(executor.calls[0][1], {"query": "improve secure app", "limit": 5})
        self.assertEqual(executor.calls[1][1], {"project_slug": "demo"})
        self.assertTrue(all(call[2] is False for call in executor.calls))

    def test_unbound_code_generation_is_not_auto_executed(self):
        executor = FakeExecutor()
        out = AgentExecutionLoop(executor=executor).run(
            report((("coding", ("code.generate",)),)),
            project_slug="demo",
        )
        self.assertFalse(executor.calls)
        self.assertEqual(out.skipped[0].status, "not_bound")

    def test_approval_gated_external_tool_never_auto_executes(self):
        tools = AgentToolRegistry()
        specialists = SpecialistAgentRegistry(tools)
        fake_release = CouncilReport(
            goal="release",
            status="ok",
            advisory_only=True,
            turns=(CouncilTurn(1, "release", result("release", ("release.publish",))),),
            requested_tools=("release.publish",),
            approval_required_tools=("release.publish",),
            budget={},
            summary="release",
        )
        executor = FakeExecutor(executable=("release.publish",))
        out = AgentExecutionLoop(
            executor=executor,
            tools=tools,
            specialists=specialists,
        ).run(fake_release, project_slug="demo")
        self.assertFalse(executor.calls)
        self.assertEqual(out.skipped[0].status, "approval_required")
        self.assertTrue(out.external_actions_blocked)

    def test_research_fetch_requires_trusted_url_context(self):
        executor = FakeExecutor(executable=("research.fetch",))
        council = report((("research", ("research.fetch",)),))
        out = AgentExecutionLoop(executor=executor).run(council, project_slug="demo")
        self.assertFalse(executor.calls)
        self.assertEqual(out.skipped[0].status, "missing_context")

    def test_tool_call_budget_is_enforced(self):
        executor = FakeExecutor()
        loop = AgentExecutionLoop(executor=executor, budget=AgentBudget(max_tool_calls=1))
        council = report((("test", ("project.inspect", "tests.run")),))
        out = loop.run(council, project_slug="demo")
        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(len(out.skipped), 1)
        self.assertIn("budget", out.skipped[0].detail.lower())


if __name__ == "__main__":
    unittest.main()
