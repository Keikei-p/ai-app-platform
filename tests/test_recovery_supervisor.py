from datetime import datetime, timezone
from pathlib import Path
import json
import tempfile
import unittest

from src.core.evaluation_engine import EvaluationReport
from src.core.recovery_supervisor import RecoverySupervisor


def report(
    score,
    *,
    tests=True,
    security=True,
    design=True,
    preview=True,
    learning=True,
):
    return EvaluationReport(
        score=score,
        tests_passed=tests,
        test_pass_ratio=1.0 if tests else 0.5,
        design_passed=design,
        design_score=95 if design else 70,
        security_passed=security,
        preview_ready=preview,
        release_ready=False,
        artifact_count=1,
        learning_eligible=learning and tests and security and design and preview,
        regressions=(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


class RecoverySupervisorTests(unittest.TestCase):
    def setUp(self):
        self.supervisor = RecoverySupervisor()

    def test_classifies_failed_test_and_allows_bounded_retry(self):
        classification = self.supervisor.classify({
            "blocking_reasons": ["automated_tests_failed"],
            "test_results": [{"name": "smoke", "passed": False}],
        })
        self.assertEqual(classification.kind, "TEST")
        self.assertTrue(classification.retryable)

        decision = self.supervisor.decide(
            report(80),
            report(80, tests=False, learning=False),
            repair_attempts=[],
            classification=classification,
        )
        self.assertEqual(decision.action, "retry")

    def test_regression_requests_recovery(self):
        classification = self.supervisor.classify({
            "blocking_reasons": ["security_gate_failed"],
            "security": {"findings": [{"key": "secret", "blocking": True}]},
        })
        decision = self.supervisor.decide(
            report(90),
            report(70, security=False, learning=False),
            repair_attempts=[{
                "attempt": 1,
                "coding": {"status": "applied"},
                "preview_ready": False,
                "blocking_reasons": ["security_gate_failed"],
            }],
            classification=classification,
        )
        self.assertEqual(decision.action, "recover")
        self.assertTrue(decision.critical_regression)

    def test_repeated_failure_stops_before_infinite_loop(self):
        classification = self.supervisor.classify({
            "blocking_reasons": ["automated_tests_failed"],
        })
        attempts = [
            {
                "attempt": 1,
                "coding": {"status": "applied"},
                "preview_ready": False,
                "blocking_reasons": ["automated_tests_failed"],
            },
            {
                "attempt": 2,
                "coding": {"status": "applied"},
                "preview_ready": False,
                "blocking_reasons": ["automated_tests_failed"],
            },
        ]
        decision = self.supervisor.decide(
            report(60, tests=False, learning=False),
            report(65, tests=False, learning=False),
            repair_attempts=attempts,
            classification=classification,
        )
        self.assertEqual(decision.action, "stop")
        self.assertTrue(decision.repeated_failure)

    def test_independent_review_requires_postflight_and_all_gates(self):
        classification = self.supervisor.classify({})
        decision = self.supervisor.decide(
            report(80),
            report(95),
            repair_attempts=[{
                "attempt": 1,
                "coding": {"status": "applied"},
                "preview_ready": True,
                "blocking_reasons": [],
            }],
            classification=classification,
        )
        review = self.supervisor.independent_review(
            report(80),
            report(95),
            decision,
            postflight_ok=True,
        )
        self.assertTrue(review.approved)

        failed = self.supervisor.independent_review(
            report(80),
            report(95),
            decision,
            postflight_ok=False,
        )
        self.assertFalse(failed.approved)
        self.assertIn("postflight", failed.findings)

    def test_learning_requires_review_certificate_and_evidence(self):
        classification = self.supervisor.classify({
            "blocking_reasons": ["automated_tests_failed"],
        })
        decision = self.supervisor.decide(
            report(80),
            report(95),
            repair_attempts=[{
                "attempt": 1,
                "coding": {"status": "applied"},
                "preview_ready": True,
                "blocking_reasons": [],
            }],
            classification=classification,
        )
        review = self.supervisor.independent_review(
            report(80),
            report(95),
            decision,
            postflight_ok=True,
        )
        learning = self.supervisor.learning_decision(
            classification=classification,
            decision=decision,
            review=review,
            certificate_verified=True,
            evidence_refs=["development_certificate.json"],
        )
        self.assertTrue(learning.promote)
        self.assertEqual(learning.status, "verified")

        rejected = self.supervisor.learning_decision(
            classification=classification,
            decision=decision,
            review=review,
            certificate_verified=False,
            evidence_refs=["development_certificate.json"],
        )
        self.assertFalse(rejected.promote)

    def test_save_is_inspectable_and_policy_bounded(self):
        classification = self.supervisor.classify({})
        baseline = report(80)
        candidate = report(95)
        decision = self.supervisor.decide(
            baseline,
            candidate,
            repair_attempts=[],
            classification=classification,
        )
        review = self.supervisor.independent_review(
            baseline,
            candidate,
            decision,
            postflight_ok=True,
        )
        with tempfile.TemporaryDirectory() as td:
            path = self.supervisor.save(
                Path(td),
                baseline=baseline,
                candidate=candidate,
                classification=classification,
                decision=decision,
                review=review,
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["policy"]["max_repair_attempts"], 2)
            self.assertFalse(data["policy"]["arbitrary_shell"])
            self.assertFalse(data["policy"]["automatic_main_merge"])
            self.assertTrue(data["policy"]["verified_learning_only"])


if __name__ == "__main__":
    unittest.main()
