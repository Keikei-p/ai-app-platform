from pathlib import Path
import tempfile
import unittest

from src.core.cost_guard import CostGuard
from src.core.secrets_guard import SecretsGuard
from src.core.stop_escalation import StopEscalationJudge
from src.core.platform_service import PlatformService


class SecretsGuardTests(unittest.TestCase):
    def test_plaintext_setting_is_reported_without_value(self):
        audit = SecretsGuard().audit_settings({
            "ai_profiles": {
                "openai": {"api_key": "sk-" + "x" * 32}
            }
        })
        self.assertFalse(audit.passed)
        self.assertIn("ai_profiles.openai.api_key", audit.plaintext_secret_fields)
        self.assertNotIn("x" * 10, " ".join(audit.findings))

    def test_dpapi_cipher_is_recognized_as_protected(self):
        audit = SecretsGuard().audit_settings({
            "ai_profiles": {"openai": {"key_cipher": "dpapi:abc123"}}
        })
        self.assertTrue(audit.passed)
        self.assertTrue(audit.protected_storage_detected)

    def test_project_secret_file_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".env").write_text("API_KEY=top-secret", encoding="utf-8")
            audit = SecretsGuard().audit_project(root)
            self.assertFalse(audit.passed)
            self.assertTrue(any(".env" in x for x in audit.findings))


class CostGuardTests(unittest.TestCase):
    def test_free_operation_never_spends_budget(self):
        guard = CostGuard(100)
        decision = guard.check(billing_mode="free")
        self.assertTrue(decision.allowed)
        self.assertEqual(guard.snapshot()["remaining_yen"], "100.00")

    def test_metered_cost_requires_explicit_approval_and_budget(self):
        guard = CostGuard(100)
        unapproved = guard.check(
            billing_mode="metered",
            estimated_cost_yen=20,
            explicitly_approved=False,
        )
        self.assertFalse(unapproved.allowed)
        self.assertTrue(unapproved.requires_human_approval)

        approved = guard.check(
            billing_mode="metered",
            estimated_cost_yen=20,
            explicitly_approved=True,
        )
        self.assertTrue(approved.allowed)
        self.assertEqual(guard.commit(approved), "20.00")
        self.assertEqual(guard.snapshot()["remaining_yen"], "80.00")

    def test_unknown_or_over_budget_cost_is_blocked(self):
        guard = CostGuard(10)
        self.assertFalse(guard.check(billing_mode="unknown").allowed)
        self.assertFalse(guard.check(
            billing_mode="metered",
            estimated_cost_yen=11,
            explicitly_approved=True,
        ).allowed)


class StopEscalationJudgeTests(unittest.TestCase):
    def test_red_and_permissions_escalate(self):
        judge = StopEscalationJudge()
        self.assertEqual(judge.decide(risk="RED").action, "ESCALATE")
        self.assertEqual(judge.decide(permission_missing=True).action, "ESCALATE")

    def test_repeated_failure_and_budget_stop(self):
        judge = StopEscalationJudge()
        first = judge.decide(
            failure_kind="TEST",
            signals=["same failure"],
        )
        repeated = judge.decide(
            failure_kind="TEST",
            signals=["same failure"],
            prior_fingerprints=[first.fingerprint],
        )
        self.assertEqual(repeated.action, "STOP")
        exhausted = judge.decide(
            failure_kind="TEST",
            attempts_used=2,
            signals=["new"],
        )
        self.assertEqual(exhausted.action, "STOP")

    def test_local_code_failure_can_continue(self):
        decision = StopEscalationJudge().decide(
            failure_kind="CODE",
            attempts_used=1,
            signals=["syntax error"],
        )
        self.assertEqual(decision.action, "CONTINUE")
        self.assertFalse(decision.requires_human)




class PlatformOperationalSafetyTests(unittest.TestCase):
    def test_service_exposes_secret_cost_and_autonomy_state(self):
        with tempfile.TemporaryDirectory() as td:
            service = PlatformService()
            service.ai_engine.settings_path = Path(td) / "settings.json"
            service.ai_engine.settings_path.write_text(
                '{"ai_profiles":{"openai":{"key_cipher":"dpapi:abc"}}}',
                encoding="utf-8",
            )
            state = service.operational_safety()
            self.assertTrue(state["secrets"]["settings"]["passed"])
            self.assertTrue(state["secrets"]["settings"]["protected_storage_detected"])
            self.assertEqual(state["cost"]["session"]["budget_yen"], "0.00")
            self.assertTrue(state["autonomy"]["repeated_failure_stops"])

    def test_service_requires_approval_before_enabling_paid_budget(self):
        service = PlatformService()
        with self.assertRaises(PermissionError):
            service.configure_cost_budget(100, approved=False)
        configured = service.configure_cost_budget(100, approved=True)
        self.assertEqual(configured["budget_yen"], "100.00")
        decision = service.check_cost_operation(
            billing_mode="metered",
            estimated_cost_yen=25,
            approved=True,
            commit=True,
        )
        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["committed_total_yen"], "25.00")
        self.assertEqual(decision["session"]["remaining_yen"], "75.00")

if __name__ == "__main__":
    unittest.main()
