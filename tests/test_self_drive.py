from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.self_drive import SelfDriveEngine


class Calls:
    def __init__(self):
        self.health = []
        self.mission = []
        self.growth = 0
        self.practice = 0


class SelfDriveTests(unittest.TestCase):
    def make_engine(self, root: Path, *, projects=None, missions=None):
        calls = Calls()
        projects = list(projects or [])
        missions = list(missions or [])

        def health(slug):
            calls.health.append(slug)
            return {
                "status": "pass",
                "tests_passed": True,
                "design_passed": True,
                "security_passed": True,
                "run_id": "health-1",
            }

        def mission_cycle(mission_id):
            calls.mission.append(mission_id)
            return {
                "mission_id": mission_id,
                "status": "approval_required",
                "phase": "build_approval",
                "requires_approval": True,
                "message": "Build approval is required.",
                "evidence_refs": ["evidence/preflight.json"],
            }

        def growth():
            calls.growth += 1
            return {
                "status": "completed",
                "skills_added": 1,
                "skills_updated": 0,
                "total_skills": 1,
            }

        def practice():
            calls.practice += 1
            return {
                "status": "completed",
                "promotion": {"promoted": True},
                "evidence_ref": "practice/evidence.json",
            }

        engine = SelfDriveEngine(
            list_projects=lambda: projects,
            health_check=health,
            list_missions=lambda: missions,
            safe_mission_cycle=mission_cycle,
            growth_cycle=growth,
            practice_cycle=practice,
            settings_path=root / "drive.json",
            history_path=root / "drive_history.jsonl",
        )
        return engine, calls

    def test_queued_mission_moves_only_to_approval_boundary(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, calls = self.make_engine(
                root,
                missions=[{
                    "mission_id": "m1",
                    "project_slug": "demo",
                    "status": "queued",
                    "requires_approval": False,
                    "build_job_id": None,
                }],
            )
            result = engine.run_cycle(trigger="test")
            self.assertEqual(result["actions_executed"], 1)
            self.assertEqual(result["task"]["kind"], "mission")
            self.assertEqual(calls.mission, ["m1"])
            self.assertTrue(result["outcome"]["requires_approval"])
            self.assertFalse(result["approval_bypassed"])
            self.assertFalse(result["main_merged"])
            self.assertFalse(result["external_published"])

    def test_approval_waiting_mission_is_never_auto_approved(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, calls = self.make_engine(
                root,
                missions=[{
                    "mission_id": "m1",
                    "project_slug": "demo",
                    "status": "approval_required",
                    "requires_approval": True,
                    "build_job_id": None,
                }],
            )
            queue = engine.plan()
            self.assertFalse(any(x.kind == "mission" for x in queue))
            result = engine.run_cycle(trigger="test")
            self.assertNotEqual(result.get("task", {}).get("kind"), "mission")
            self.assertEqual(calls.mission, [])

    def test_one_cycle_executes_only_highest_priority_safe_task(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, calls = self.make_engine(
                root,
                projects=[{
                    "slug": "broken",
                    "quality": "BLOCKED",
                    "status": "attention_required",
                }],
                missions=[],
            )
            result = engine.run_cycle(trigger="test")
            self.assertEqual(result["actions_executed"], 1)
            self.assertEqual(result["task"]["kind"], "project_health")
            self.assertEqual(calls.health, ["broken"])
            self.assertEqual(calls.growth, 0)
            self.assertEqual(calls.practice, 0)

    def test_cooldown_advances_to_next_safe_task(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, calls = self.make_engine(
                root,
                projects=[{
                    "slug": "broken",
                    "quality": "BLOCKED",
                    "status": "attention_required",
                }],
            )
            first = engine.run_cycle(trigger="test")
            second = engine.run_cycle(trigger="test")
            self.assertEqual(first["task"]["kind"], "project_health")
            self.assertEqual(second["task"]["kind"], "growth")
            self.assertEqual(calls.health, ["broken"])
            self.assertEqual(calls.growth, 1)

    def test_failed_safe_action_is_recorded_and_does_not_raise(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = Calls()

            def broken_health(slug):
                calls.health.append(slug)
                raise RuntimeError("synthetic health failure")

            engine = SelfDriveEngine(
                list_projects=lambda: [{
                    "slug": "broken",
                    "quality": "BLOCKED",
                    "status": "attention_required",
                }],
                health_check=broken_health,
                list_missions=lambda: [],
                safe_mission_cycle=lambda mission_id: {},
                growth_cycle=lambda: {"status": "completed"},
                practice_cycle=lambda: {"status": "completed"},
                settings_path=root / "drive.json",
                history_path=root / "drive_history.jsonl",
            )
            result = engine.run_cycle(trigger="test")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["outcome"]["error_type"], "RuntimeError")
            self.assertEqual(calls.health, ["broken"])
            self.assertTrue(engine.recent(1))

    def test_after_cycle_observer_runs_without_changing_execution(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, calls = self.make_engine(root)
            observed = []
            engine.set_after_cycle(lambda result: observed.append(result["status"]))
            result = engine.run_cycle(trigger="test")
            self.assertEqual(result["actions_executed"], 1)
            self.assertEqual(observed, ["completed"])
            self.assertEqual(calls.growth, 1)

    def test_deep_practice_is_not_scheduled_by_self_drive(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, calls = self.make_engine(root)
            queue = engine.plan()
            self.assertFalse(any(x.kind == "practice" for x in queue))
            self.assertEqual(engine.status()["practice_cadence"], "daily_evolution_only")
            engine.run_cycle(trigger="test")
            self.assertEqual(calls.practice, 0)

    def test_status_exposes_hard_protection_boundaries(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, _ = self.make_engine(root)
            status = engine.status()
            self.assertTrue(status["enabled"])
            self.assertEqual(status["max_actions_per_cycle"], 1)
            self.assertFalse(status["source_self_edit_allowed"])
            self.assertFalse(status["main_merge_allowed"])
            self.assertFalse(status["production_deploy_allowed"])
            self.assertFalse(status["external_publish_allowed"])
            self.assertFalse(status["paid_actions_allowed"])
            self.assertFalse(status["secret_access_allowed"])
            self.assertFalse(status["production_database_write_allowed"])
            self.assertFalse(status["approval_bypass_allowed"])
            self.assertIn("approval_bypass", status["protected_actions"])


    def test_string_false_disables_self_drive_and_invalid_interval_recovers(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, _ = self.make_engine(root)
            (root / "drive.json").write_text(
                '{"enabled": "false", "interval_seconds": "invalid", "allow_main_merge": true}',
                encoding="utf-8",
            )
            cfg = engine.settings()
            self.assertFalse(cfg["enabled"])
            self.assertEqual(cfg["interval_seconds"], 600)
            self.assertFalse(cfg["allow_main_merge"])
            self.assertEqual(engine.run_cycle(trigger="test")["status"], "disabled")

    def test_corrupt_policy_fails_closed_instead_of_resuming_background_work(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, _ = self.make_engine(root)
            (root / "drive.json").write_text("{not valid json", encoding="utf-8")
            self.assertFalse(engine.settings()["enabled"])
            self.assertEqual(engine.settings()["config_error"], "unreadable_settings")

    def test_background_planning_exception_is_recorded_without_sensitive_message(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, _ = self.make_engine(root)
            observed = []
            engine.list_missions = lambda: (_ for _ in ()).throw(
                RuntimeError("private-token-do-not-log")
            )
            engine.set_after_cycle(lambda result: observed.append(result["status"]))
            engine._background_step()
            latest = engine.recent(1)[0]
            self.assertEqual(latest["status"], "failed")
            self.assertEqual(latest["outcome"]["error_type"], "RuntimeError")
            self.assertNotIn("private-token-do-not-log", str(latest))
            self.assertEqual(observed, ["failed"])

    def test_reported_failure_does_not_claim_successful_autonomous_cycle(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, _ = self.make_engine(root)
            engine.growth_cycle = lambda: {
                "status": "failed",
                "skills_added": 0,
                "skills_updated": 0,
                "total_skills": 0,
            }
            result = engine.run_cycle(trigger="test")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(engine.recent(1)[0]["status"], "failed")

    def test_failed_project_health_is_not_reported_as_completed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, _ = self.make_engine(
                root,
                projects=[{"slug": "needs-attention", "quality": "BLOCKED", "status": "issue"}],
            )
            engine.health_check = lambda slug: {
                "status": "fail",
                "tests_passed": False,
                "design_passed": True,
                "security_passed": True,
            }
            self.assertEqual(engine.run_cycle(trigger="test")["status"], "failed")


if __name__ == "__main__":
    unittest.main()
