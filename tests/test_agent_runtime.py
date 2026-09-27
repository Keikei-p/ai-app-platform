import tempfile
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.core.agent_runtime import AgentOrchestrator, EvidenceLedger
from src.core.test_runner import TestResult
from src.core.design_ai import DesignReview
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
    def _write_verified_reports(self, project: Path):
        reports = project / ".aiapp" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "test_report.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
        (reports / "security_report.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
        (reports / "build_readiness.json").write_text(json.dumps({"preview_ready": True}), encoding="utf-8")
        (reports / "agent_evaluation.json").write_text(json.dumps({"score": 95}), encoding="utf-8")
        (reports / "release_manager.json").write_text(
            json.dumps({"all_requested_artifacts_ready": False, "targets": [{"target": "web"}]}),
            encoding="utf-8",
        )
        (project / "design_review.json").write_text(
            json.dumps({"passed": True, "score": 95}),
            encoding="utf-8",
        )

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


    def test_build_project_attaches_verified_agent_execution_trace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "demo"
            project.mkdir()
            (project / "project.json").write_text('{"name":"Demo","slug":"demo"}', encoding="utf-8")
            self._write_verified_reports(project)

            service = PlatformService()
            service.core = SimpleNamespace(
                execute=lambda *args, **kwargs: SimpleNamespace(
                    ok=True,
                    message="ok",
                    pipeline_report={"security": {"passed": True}},
                    tests=[TestResult("demo", True, "ok")],
                    design_review=DesignReview(95, True, [], []),
                    repair_attempts=[],
                    plan={"spec": {"targets": ["web"]}},
                    windows_build=None,
                    web_build={"built": True, "artifact": "demo.zip"},
                    android_build=None,
                    ios_source_build=None,
                )
            )
            with patch("src.core.platform_service.WORKSPACE_DIR", root):
                result = service.build_project("demo", "build demo", approved=True)
            trace = (result.pipeline_report or {}).get("agent_execution_trace") or {}
            self.assertEqual(trace.get("status"), "verified")
            self.assertTrue(result.ok)
            self.assertTrue((project / trace["history_path"]).is_file())

    def test_build_project_blocks_self_asserted_completion_without_completion_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "demo"
            project.mkdir()
            (project / "project.json").write_text('{"name":"Demo","slug":"demo"}', encoding="utf-8")

            service = PlatformService()
            service.core = SimpleNamespace(
                execute=lambda *args, **kwargs: SimpleNamespace(
                    ok=True,
                    message="claimed complete",
                    pipeline_report={"security": {"passed": True}},
                    tests=[TestResult("demo", True, "ok")],
                    design_review=DesignReview(95, True, [], []),
                    repair_attempts=[],
                    plan={"spec": {"targets": ["web"]}},
                    windows_build=None,
                    web_build={"built": True, "artifact": "demo.zip"},
                    android_build=None,
                    ios_source_build=None,
                )
            )
            service.agent.completion_check = lambda *args, **kwargs: {
                "complete": False,
                "missing_evidence": ["report"],
                "blocking_evidence": [],
                "rule": "evidence required",
            }
            with patch("src.core.platform_service.WORKSPACE_DIR", root):
                result = service.build_project("demo", "build demo", approved=True)
            self.assertFalse(result.ok)
            self.assertIn("Evidence", result.message)
            self.assertFalse((result.pipeline_report or {})["agent_completion"]["complete"])

    def test_tkinter_build_path_uses_platform_service_completion_gate(self):
        source = (Path(__file__).resolve().parents[1] / "src" / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn("PlatformService", source)
        self.assertIn("self.platform.build_project(", source)
        self.assertNotIn("self.core.execute(", source)

if __name__ == "__main__":
    unittest.main()
