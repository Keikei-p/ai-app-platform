import tempfile
import unittest
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.dependency_guardian import DependencyGuardian
from src.core.evaluation_engine import EvaluationReport
from src.core.regression_guardian import RegressionGuardian
from src.core.requirement_guardian import RequirementGuardian


def evaluation(score=90, tests=True, security=True, design=True, preview=True, release=False, artifacts=1):
    return EvaluationReport(
        score=score,
        tests_passed=tests,
        test_pass_ratio=1.0 if tests else 0.5,
        design_passed=design,
        design_score=95 if design else 50,
        security_passed=security,
        preview_ready=preview,
        release_ready=release,
        artifact_count=artifacts,
        learning_eligible=tests and security and design and preview,
        regressions=(),
        created_at="2026-01-01T00:00:00+00:00",
    )


class RegressionGuardianTests(unittest.TestCase):
    def test_previous_passing_gate_regression_blocks_completion(self):
        report = RegressionGuardian().compare(
            evaluation(score=92, tests=True),
            evaluation(score=95, tests=False),
        )
        self.assertTrue(report.blocked)
        self.assertIn("tests", report.critical_regressions)

    def test_score_drop_without_gate_failure_warns_but_does_not_block(self):
        report = RegressionGuardian().compare(
            evaluation(score=92),
            evaluation(score=88),
        )
        self.assertFalse(report.blocked)
        self.assertTrue(report.warnings)


class RequirementGuardianTests(unittest.TestCase):
    def test_requirement_ledger_never_claims_semantic_proof(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "app_spec.json").write_text("{}", encoding="utf-8")
            report_dir = root / ".aiapp" / "reports"
            report_dir.mkdir(parents=True)
            for name in ("test_report.json", "security_report.json", "build_readiness.json"):
                (report_dir / name).write_text("{}", encoding="utf-8")
            spec = AppSpec(
                project_name="Demo",
                slug="demo",
                summary="demo",
                app_type="web",
                features=["login", "dashboard"],
                targets=["web"],
            )
            report = RequirementGuardian().assess(
                root,
                spec,
                instruction="build login dashboard",
                pipeline_report={"agent_postflight": {"status": "pass"}},
                trace={"history_path": ".aiapp/agent/runs/run.json"},
            )
            self.assertEqual(report.status, "review_required")
            self.assertTrue(report.semantic_review_required)
            self.assertEqual(report.requirements[0].status, "pipeline_evidence_present")

    def test_empty_feature_spec_is_structurally_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            spec = AppSpec("Demo", "demo", "demo", "web", [], ["web"])
            report = RequirementGuardian().assess(
                root, spec, instruction="build", pipeline_report={}, trace={}
            )
            self.assertEqual(report.status, "blocked")
            self.assertTrue(report.structural_blockers)


class DependencyGuardianTests(unittest.TestCase):
    def test_detects_floating_dependency_without_online_cve_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "package.json").write_text(
                '{"dependencies":{"unsafe":"latest","ok":"^1.2.3"}}',
                encoding="utf-8",
            )
            report = DependencyGuardian().scan(root)
            self.assertEqual(report.status, "attention_required")
            self.assertTrue(any(x.severity == "high" for x in report.findings))
            self.assertFalse(report.online_vulnerability_check_performed)


if __name__ == "__main__":
    unittest.main()
