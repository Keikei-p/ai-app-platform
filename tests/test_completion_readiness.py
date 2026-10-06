from __future__ import annotations

import unittest

from src.core.completion_readiness import CompletionReadinessEngine


def full_caps():
    return {
        "context_aware_conversation": True,
        "long_conversation_continuity": True,
        "conversation_intent_routing": True,
        "typo_tolerant_language_understanding": True,
        "local_ollama_conversation_fallback": True,
        "web": True,
        "windows": True,
        "android": True,
        "ios_source": True,
        "ios_signed_ipa": False,
        "social_automation": True,
        "artifact_catalog": True,
        "cross_mode_real_app_e2e_verified": True,
        "agent_planning": True,
        "specialist_agents": 10,
        "reviewed_tool_executor": True,
        "specialist_execution_council": True,
        "parallel_sandbox_workers": True,
        "source_write_single_coordinator": True,
        "project_health_check": True,
        "development_certificate": True,
        "regression_guardian": True,
        "requirement_guardian": True,
        "dependency_guardian": True,
        "accessibility_guardian": True,
        "performance_guardian": True,
        "release_guardian": True,
        "recovery_supervisor": True,
        "independent_recovery_review": True,
        "validated_recovery_learning": True,
        "verified_learning_flywheel": True,
        "candidate_arena": True,
        "model_benchmark_store": True,
        "self_drive_scheduler": True,
        "self_drive_priority_queue": True,
        "self_drive_approval_boundary": True,
        "persistent_daily_backlog": True,
        "daily_evolution_engine": True,
        "daily_evolution_catchup": True,
        "daily_evolution_single_practice": True,
        "strategic_long_term_goals": True,
        "automatic_bounded_mission_generation": True,
        "strategic_mission_approval_boundary": True,
        "multi_mission_end_to_end_verified": True,
        "release_manager": True,
        "observable_build_jobs": True,
        "production_monitor": True,
        "cost_guard": True,
        "secrets_guard": True,
        "long_run_soak_verified": True,
        "cloud_runtime_ready": True,
        "dedicated_credential_store": True,
        "connector_registry": True,
        "credential_free_config_export": True,
        "transfer_audit": True,
        "non_destructive_transfer_package": True,
        "ownership_profile": True,
        "oem_branding_foundation": True,
        "buyer_productization_e2e_verified": True,
    }


class CompletionReadinessTests(unittest.TestCase):
    def make_engine(self, caps):
        return CompletionReadinessEngine(
            capability_snapshot=lambda: dict(caps),
            self_drive_status=lambda: {
                "enabled": True,
                "background_active": True,
                "approval_bypass_allowed": False,
            },
            daily_evolution_status=lambda: {
                "enabled": True,
                "background_active": True,
                "source_self_edit_allowed": False,
            },
            strategic_status=lambda: {
                "build_auto_approval": False,
                "max_missions_created_per_cycle": 1,
            },
            learning_status=lambda: {
                "verified_examples": 25,
                "average_score": 96.5,
            },
            health_status=lambda: {"status": "healthy"},
        )

    def test_full_evidence_can_reach_100_without_auto_publish(self):
        report = self.make_engine(full_caps()).assess()
        self.assertEqual(report["percentage"], 100.0)
        self.assertTrue(report["complete"])
        self.assertEqual(report["gaps"], [])
        self.assertTrue(report["external_dependencies"])
        self.assertIn("iOS", report["external_dependencies"][0])

    def test_missing_real_world_evidence_prevents_100(self):
        caps = full_caps()
        caps["cross_mode_real_app_e2e_verified"] = False
        caps["multi_mission_end_to_end_verified"] = False
        caps["long_run_soak_verified"] = False
        caps["cloud_runtime_ready"] = False

        report = self.make_engine(caps).assess()

        self.assertFalse(report["complete"])
        self.assertLess(report["percentage"], 100)
        missing = {
            item
            for gap in report["gaps"]
            for item in gap["missing"]
        }
        self.assertIn("cross-mode real E2E", missing)
        self.assertIn("multi-mission E2E", missing)
        self.assertIn("24h soak evidence", missing)
        self.assertIn("cloud runtime ready", missing)

    def test_missing_buyer_journey_e2e_prevents_productization_pass(self):
        caps = full_caps()
        caps["buyer_productization_e2e_verified"] = False
        report = self.make_engine(caps).assess()
        self.assertFalse(report["complete"])
        product = next(
            x for x in report["criteria"]
            if x["criterion_id"] == "productization"
        )
        self.assertIn("buyer journey E2E", product["gaps"])

    def test_runtime_autonomy_must_be_enabled_for_full_score(self):
        engine = CompletionReadinessEngine(
            capability_snapshot=full_caps,
            self_drive_status=lambda: {
                "enabled": False,
                "background_active": False,
                "approval_bypass_allowed": False,
            },
            daily_evolution_status=lambda: {
                "enabled": True,
                "background_active": True,
                "source_self_edit_allowed": False,
            },
            strategic_status=lambda: {
                "build_auto_approval": False,
                "max_missions_created_per_cycle": 1,
            },
            learning_status=lambda: {},
            health_status=lambda: {"status": "healthy"},
        )
        report = engine.assess()
        self.assertFalse(report["complete"])
        autonomy = next(x for x in report["criteria"] if x["criterion_id"] == "autonomy")
        self.assertIn("runtime enabled", autonomy["gaps"])
        self.assertIn("background active", autonomy["gaps"])

    def test_health_failure_reduces_operations_score(self):
        engine = CompletionReadinessEngine(
            capability_snapshot=full_caps,
            self_drive_status=lambda: {
                "enabled": True,
                "background_active": True,
                "approval_bypass_allowed": False,
            },
            daily_evolution_status=lambda: {
                "enabled": True,
                "background_active": True,
                "source_self_edit_allowed": False,
            },
            strategic_status=lambda: {
                "build_auto_approval": False,
                "max_missions_created_per_cycle": 1,
            },
            learning_status=lambda: {},
            health_status=lambda: {"status": "critical"},
        )
        report = engine.assess()
        operations = next(x for x in report["criteria"] if x["criterion_id"] == "operations")
        self.assertLess(operations["score"], operations["weight"])
        self.assertIn("health guarded", operations["gaps"])


if __name__ == "__main__":
    unittest.main()
