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


if __name__ == "__main__":
    unittest.main()
