import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.core.agent_execution_trace import BuildExecutionTracer
from src.core.agent_runtime import AgentOrchestrator
from src.core.test_runner import TestResult
from src.core.design_ai import DesignReview


class BuildExecutionTracerTests(unittest.TestCase):
    def _result(self, *, ok=True, tests=True, design=True, security=True, repairs=None):
        return SimpleNamespace(
            ok=ok,
            pipeline_report={"security": {"passed": security}},
            tests=[TestResult("demo", tests, "ok" if tests else "fail")],
            design_review=DesignReview(95 if design else 70, design, [], []),
            repair_attempts=repairs or [],
            plan={"spec": {"targets": ["web"]}},
            windows_build=None,
            web_build={"built": ok, "artifact": "demo.zip" if ok else None},
            android_build=None,
            ios_source_build=None,
        )

    def test_verified_build_maps_real_gates_to_agent_steps(self):
        plan = AgentOrchestrator().plan("demo", "demo")
        with tempfile.TemporaryDirectory() as td:
            trace = BuildExecutionTracer().create(plan, self._result(), Path(td))
            self.assertEqual(trace.status, "verified")
            rows = {x.step_id: x for x in trace.steps}
            self.assertEqual(rows["validate-tests"].status, "pass")
            self.assertEqual(rows["validate-design"].status, "pass")
            self.assertEqual(rows["validate-security"].status, "pass")
            self.assertEqual(rows["review"].status, "approval_required")
            self.assertTrue((Path(td) / trace.history_path).is_file())

    def test_failed_security_blocks_verified_trace(self):
        plan = AgentOrchestrator().plan("demo", "demo")
        with tempfile.TemporaryDirectory() as td:
            trace = BuildExecutionTracer().create(
                plan,
                self._result(ok=False, security=False),
                Path(td),
            )
            self.assertEqual(trace.status, "blocked")
            rows = {x.step_id: x for x in trace.steps}
            self.assertEqual(rows["validate-security"].status, "fail")
            self.assertEqual(rows["report"].status, "blocked")


if __name__ == "__main__":
    unittest.main()
