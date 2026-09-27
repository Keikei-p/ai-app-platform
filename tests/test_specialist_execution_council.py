import json
import tempfile
import unittest
from pathlib import Path

from src.core.agent_tool_executor import AgentToolExecution
from src.core.agent_tools import AgentToolRegistry
from src.core.specialist_agents import SpecialistAgentRegistry
from src.core.specialist_execution_council import SpecialistExecutionCouncil


class FakeStatus:
    connected = True


class EvidenceSeekingEngine:
    def __init__(self):
        self.calls = []

    def status(self):
        return FakeStatus()

    def settings(self):
        return {"provider": "fake", "model": "fake-model"}

    def reply(self, history, user_text, system_instruction):
        payload = json.loads(user_text)
        system = str(system_instruction)
        self.calls.append(payload)
        if "Research AI" in system:
            requested = ["knowledge.search"]
        elif "Architecture AI" in system:
            requested = ["project.inspect"]
        elif "Coding AI" in system:
            requested = ["code.generate"]
        elif "Test AI" in system:
            requested = ["tests.run"]
        elif "Design AI" in system:
            requested = ["design.review"]
        elif "Security AI" in system:
            requested = ["security.scan"]
        elif "Build AI" in system:
            requested = ["package.build"]
        else:
            requested = ["project.inspect"]
        return json.dumps({
            "summary": "checked",
            "findings": [],
            "recommendations": [],
            "requested_tools": requested,
            "uncertainties": [],
        })


class FakeExecutor:
    def __init__(self):
        self.registry = AgentToolRegistry()
        self.calls = []

    def executable_tools(self):
        return (
            "project.inspect",
            "knowledge.search",
            "tests.run",
            "design.review",
            "security.scan",
            "package.build",
        )

    def execute(self, name, args, approved=False, run_id=""):
        self.calls.append((name, dict(args), approved, run_id))
        results = {
            "project.inspect": {"project": {"name": "Demo"}},
            "knowledge.search": {"knowledge": [{"statement": "verified"}]},
            "tests.run": {"passed": True, "results": []},
            "design.review": {"review": {"passed": True, "score": 96}},
            "security.scan": {"security": {"passed": True, "findings": []}},
        }
        return AgentToolExecution(name, "executed", "validate", False, results[name])


class SpecialistExecutionCouncilTests(unittest.TestCase):
    def test_only_reviewed_read_and_validation_tools_execute(self):
        engine = EvidenceSeekingEngine()
        executor = FakeExecutor()
        report = SpecialistExecutionCouncil(
            engine=engine,
            executor=executor,
            tools=executor.registry,
            specialists=SpecialistAgentRegistry(executor.registry),
        ).run("improve demo", "demo")

        self.assertEqual(report.status, "completed")
        self.assertEqual(
            set(report.executed_tools),
            {"project.inspect", "knowledge.search", "tests.run", "design.review", "security.scan"},
        )
        self.assertIn("code.generate", report.delegated_tools)
        self.assertIn("package.build", report.delegated_tools)
        self.assertNotIn("code.generate", [x[0] for x in executor.calls])
        self.assertNotIn("package.build", [x[0] for x in executor.calls])
        self.assertEqual(report.approval_required_tools, ())
        self.assertEqual(report.execution_mode, "reviewed_local_validation_only")

    def test_tool_evidence_is_shared_with_later_specialists(self):
        engine = EvidenceSeekingEngine()
        executor = FakeExecutor()
        SpecialistExecutionCouncil(
            engine=engine,
            executor=executor,
            tools=executor.registry,
            specialists=SpecialistAgentRegistry(executor.registry),
        ).run("improve demo", "demo", roles=("research", "architect"))
        second_context = engine.calls[1]["context"]
        evidence = second_context.get("verified_tool_evidence") or []
        self.assertEqual(evidence[0]["tool_name"], "knowledge.search")

    def test_repeated_tool_request_is_reused_not_reexecuted(self):
        engine = EvidenceSeekingEngine()
        executor = FakeExecutor()
        report = SpecialistExecutionCouncil(
            engine=engine,
            executor=executor,
            tools=executor.registry,
            specialists=SpecialistAgentRegistry(executor.registry),
        ).run("inspect demo", "demo", roles=("architect", "coordinator"))
        project_calls = [x for x in executor.calls if x[0] == "project.inspect"]
        self.assertEqual(len(project_calls), 1)
        self.assertTrue(any(x.status == "reused" for x in report.tool_executions))

    def test_all_validation_tool_results_create_verified_evidence_state(self):
        executor = FakeExecutor()
        report = SpecialistExecutionCouncil(
            engine=EvidenceSeekingEngine(),
            executor=executor,
        ).run(
            "verify demo",
            "demo",
            roles=("test", "design", "security", "coordinator"),
        )
        self.assertEqual(report.evidence_state, "verified")
        self.assertTrue(report.validation["checks"]["tests.run"])
        self.assertTrue(report.validation["checks"]["design.review"])
        self.assertTrue(report.validation["checks"]["security.scan"])
        self.assertTrue(report.external_actions_blocked)

    def test_partial_evidence_is_not_called_verified(self):
        executor = FakeExecutor()
        report = SpecialistExecutionCouncil(
            engine=EvidenceSeekingEngine(),
            executor=executor,
        ).run("test demo", "demo", roles=("test",))
        self.assertEqual(report.evidence_state, "partial")

    def test_release_role_cannot_enter_execution_council(self):
        executor = FakeExecutor()
        with self.assertRaises(ValueError):
            SpecialistExecutionCouncil(
                engine=EvidenceSeekingEngine(),
                executor=executor,
            ).run("publish", "demo", roles=("release",))


    def test_each_execution_council_run_has_unique_audit_id(self):
        executor = FakeExecutor()
        council = SpecialistExecutionCouncil(
            engine=EvidenceSeekingEngine(),
            executor=executor,
        )
        first = council.run("inspect demo", "demo", roles=("architect",))
        second = council.run("inspect demo", "demo", roles=("architect",))
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertTrue(first.run_id.startswith("council-"))

    def test_persisted_history_omits_raw_tool_results(self):
        executor = FakeExecutor()
        report = SpecialistExecutionCouncil(
            engine=EvidenceSeekingEngine(),
            executor=executor,
        ).run("password=super-secret-value inspect demo", "demo", roles=("architect",))
        with tempfile.TemporaryDirectory() as td:
            path = SpecialistExecutionCouncil.save(Path(td), report)
            text = path.read_text(encoding="utf-8")
            self.assertIn(report.run_id, text)
            self.assertNotIn("super-secret-value", text)
            self.assertNotIn('"result"', text)
            self.assertIn("[REDACTED]", text)

if __name__ == "__main__":
    unittest.main()
