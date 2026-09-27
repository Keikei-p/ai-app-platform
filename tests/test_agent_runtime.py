import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.agent_runtime import AgentOrchestrator, EvidenceLedger
from src.core.platform_service import PlatformService


class AgentRuntimeTests(unittest.TestCase):
    def test_agent_plan_is_bounded_and_transparent(self):
        plan = AgentOrchestrator().plan("予約アプリを改善する", "demo")
        self.assertEqual(plan.max_repair_attempts, 2)
        self.assertEqual(plan.steps[0].action, "understand")
        self.assertEqual(plan.steps[-1].action, "report")
        self.assertTrue(any(x.requires_human_approval for x in plan.steps))
        self.assertFalse(any(x.action == "shell" for x in plan.steps))

    def test_unverified_outcome_is_not_learned(self):
        result = AgentOrchestrator().learn_from_verified_outcome(
            goal="test", lesson="guess", outcome="unknown", verified=False
        )
        self.assertFalse(result["recorded"])

    def test_evidence_ledger_is_append_only_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ledger = EvidenceLedger(root)
            one = ledger.record(
                run_id="run-1", stage="plan", status="ready",
                summary="plan ready", source="unit-test"
            )
            two = ledger.record(
                run_id="run-1", stage="validate", status="pass",
                summary="tests passed", source="unit-test"
            )
            self.assertNotEqual(one.evidence_id, two.evidence_id)
            rows = ledger.recent()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[-1].stage, "validate")
            self.assertEqual(len(rows[-1].sha256), 64)


class PlatformServiceTests(unittest.TestCase):
    def test_service_exposes_headless_capabilities(self):
        status = PlatformService().status()
        self.assertEqual(status["architecture"], "local-first-core-service")
        self.assertTrue(status["capabilities"]["agent_planning"])
        self.assertTrue(status["capabilities"]["persistent_conversations"])

    def test_build_requires_explicit_approval_before_core_execution(self):
        service = PlatformService()
        with self.assertRaises(PermissionError):
            service.build_project("does-not-matter", "build it", approved=False)

    def test_agent_plan_available_without_ui(self):
        service = PlatformService()
        plan = service.agent_plan("SNS投稿アプリを改善する", "sns")
        self.assertEqual(plan["project_slug"], "sns")
        self.assertGreaterEqual(len(plan["steps"]), 8)
        self.assertTrue(plan["steps"][-2]["requires_human_approval"])


if __name__ == "__main__":
    unittest.main()
