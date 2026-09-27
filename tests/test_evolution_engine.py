import unittest
from datetime import datetime, timezone

from src.core.evaluation_engine import EvaluationReport
from src.core.evolution_engine import VerifiedEvolutionEngine


def report(
    score,
    *,
    tests=True,
    security=True,
    design=True,
    preview=True,
    release=False,
):
    return EvaluationReport(
        score=score,
        tests_passed=tests,
        test_pass_ratio=1.0 if tests else 0.5,
        design_passed=design,
        design_score=95 if design else 70,
        security_passed=security,
        preview_ready=preview,
        release_ready=release,
        artifact_count=1,
        learning_eligible=tests and security and design and preview,
        regressions=(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


class VerifiedEvolutionEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = VerifiedEvolutionEngine()
        self.baseline = report(90)

    def test_better_verified_candidate_only_reaches_human_review(self):
        decision = self.engine.compare(
            self.baseline,
            report(94),
            changed_paths=["src/core/generator.py", "tests/test_generator.py"],
            evidence_refs=["ci:123", "security:pass", "design:94"],
        )
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.status, "human_review_required")
        self.assertFalse(decision.policy.auto_apply)
        self.assertFalse(decision.policy.auto_merge_main)

    def test_equal_or_lower_score_is_rejected(self):
        for score in (90, 89):
            decision = self.engine.compare(
                self.baseline,
                report(score),
                changed_paths=["src/core/generator.py"],
                evidence_refs=["ci:123"],
            )
            self.assertFalse(decision.eligible)
            self.assertEqual(decision.status, "rejected")

    def test_critical_regression_rejects_candidate_even_if_score_is_higher(self):
        decision = self.engine.compare(
            self.baseline,
            report(96, security=False),
            changed_paths=["src/core/generator.py"],
            evidence_refs=["ci:123"],
        )
        self.assertFalse(decision.eligible)
        self.assertTrue(decision.critical_regression)
        self.assertTrue(any("regression" in x for x in decision.blockers))

    def test_root_policy_change_is_always_rejected(self):
        for path in (
            "src/core/safety.py",
            "src/core/permissions.py",
            "src/core/agent_tools.py",
            "src/tools/security_selfcheck.py",
            ".github/workflows/ci.yml",
        ):
            decision = self.engine.compare(
                self.baseline,
                report(99),
                changed_paths=[path],
                evidence_refs=["ci:123"],
            )
            self.assertFalse(decision.eligible, path)
            self.assertIn(path, decision.protected_changes)

    def test_missing_evidence_is_rejected(self):
        decision = self.engine.compare(
            self.baseline,
            report(95),
            changed_paths=["src/core/generator.py"],
            evidence_refs=[],
        )
        self.assertFalse(decision.eligible)
        self.assertTrue(any("evidence" in x for x in decision.blockers))

    def test_forbidden_autonomous_merge_or_publish_is_rejected(self):
        for action in ("merge_main", "production_deploy", "store_submit", "disable_safety"):
            decision = self.engine.compare(
                self.baseline,
                report(97),
                changed_paths=["src/core/generator.py"],
                evidence_refs=["ci:123"],
                requested_actions=[action],
            )
            self.assertFalse(decision.eligible, action)

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            self.engine.compare(
                self.baseline,
                report(95),
                changed_paths=["../safety.py"],
                evidence_refs=["ci:123"],
            )


if __name__ == "__main__":
    unittest.main()
