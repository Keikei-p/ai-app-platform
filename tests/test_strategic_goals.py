from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.strategic_goals import StrategicGoalStore, StrategicAutonomyEngine


class StrategicGoalTests(unittest.TestCase):
    def make_engine(self, root: Path):
        projects = [{
            "slug": "demo",
            "name": "Demo",
            "quality": "PASS",
            "status": "ready",
        }]
        missions = []
        created = []

        def project_detail(slug):
            return {
                "readiness": {
                    "preview_ready": True,
                    "release_ready": False,
                },
                "gaps": {
                    "items": [{"reason": "release guardian not complete"}],
                },
            }

        def create_mission(**kwargs):
            mission = {
                "mission_id": f"m{len(created)+1}",
                "project_slug": kwargs["project_slug"],
                "goal": kwargs["goal"],
                "status": "queued",
                "requires_approval": False,
                "evidence_refs": [],
            }
            created.append(mission)
            missions.append(mission)
            return mission

        store = StrategicGoalStore(root / "goals.json")
        engine = StrategicAutonomyEngine(
            store=store,
            list_projects=lambda: projects,
            project_detail=project_detail,
            list_missions=lambda: list(missions),
            create_mission=create_mission,
            history_path=root / "strategic_history.jsonl",
        )
        return engine, store, projects, missions, created

    def test_long_term_goal_creates_only_one_bounded_mission(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, store, _, missions, created = self.make_engine(root)
            goal = engine.create_goal(
                project_slug="demo",
                objective="初心者でも迷わない完成版へ育てる",
            )

            first = engine.run_cycle(trigger="test")
            second = engine.run_cycle(trigger="test")

            self.assertTrue(first["mission_created"])
            self.assertFalse(first["build_auto_approved"])
            self.assertEqual(len(created), 1)
            self.assertEqual(second["status"], "waiting_on_mission")
            self.assertEqual(len(created), 1)
            saved = store.get(goal["goal_id"])
            self.assertEqual(saved.current_mission_id, "m1")
            self.assertEqual(saved.missions_created, 1)

    def test_completed_mission_allows_next_milestone(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, store, _, missions, created = self.make_engine(root)
            goal = engine.create_goal(
                project_slug="demo",
                objective="公開前品質まで継続改善する",
            )
            first = engine.run_cycle(trigger="test")
            self.assertEqual(first["status"], "mission_created")

            missions[0]["status"] = "completed"
            missions[0]["evidence_refs"] = ["evidence/m1.json"]
            second = engine.run_cycle(trigger="test")

            self.assertEqual(second["status"], "mission_created")
            self.assertEqual(len(created), 2)
            saved = store.get(goal["goal_id"])
            self.assertIn("m1", saved.completed_mission_ids)
            self.assertEqual(saved.current_mission_id, "m2")
            self.assertEqual(saved.missions_created, 2)

    def test_approval_waiting_mission_blocks_new_mission(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, _, _, missions, created = self.make_engine(root)
            engine.create_goal(
                project_slug="demo",
                objective="高品質な完成版へ育てる",
            )
            engine.run_cycle(trigger="test")
            missions[0]["status"] = "approval_required"
            missions[0]["requires_approval"] = True

            row = engine.run_cycle(trigger="test")
            self.assertEqual(row["status"], "waiting_on_mission")
            self.assertTrue(row["requires_approval"])
            self.assertEqual(len(created), 1)

    def test_mission_budget_pauses_goal(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, store, _, missions, _ = self.make_engine(root)
            goal = engine.create_goal(
                project_slug="demo",
                objective="継続改善する",
                max_auto_missions=1,
            )
            engine.run_cycle(trigger="test")
            missions[0]["status"] = "completed"

            row = engine.run_cycle(trigger="test")
            self.assertEqual(row["status"], "mission_budget_reached")
            self.assertEqual(store.get(goal["goal_id"]).status, "paused")

    def test_missing_project_pauses_goal_safely(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, store, projects, _, _ = self.make_engine(root)
            goal = engine.create_goal(
                project_slug="demo",
                objective="継続改善する",
            )
            projects.clear()

            row = engine.run_cycle(trigger="test")
            self.assertEqual(row["status"], "paused")
            self.assertEqual(row["reason"], "project_missing")
            self.assertEqual(store.get(goal["goal_id"]).status, "paused")

    def test_goal_controls_persist_without_deleting_project_data(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, store, _, _, _ = self.make_engine(root)
            goal = engine.create_goal(
                project_slug="demo",
                objective="長期改善する",
            )
            paused = store.pause(goal["goal_id"])
            resumed = store.resume(goal["goal_id"])
            cancelled = store.cancel(goal["goal_id"])

            self.assertEqual(paused.status, "paused")
            self.assertEqual(resumed.status, "active")
            self.assertEqual(cancelled.status, "cancelled")
            self.assertTrue((root / "goals.json").is_file())


if __name__ == "__main__":
    unittest.main()
