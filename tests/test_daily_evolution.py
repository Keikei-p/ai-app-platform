from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.daily_evolution import DailyEvolutionEngine


class Calls:
    def __init__(self):
        self.growth = 0
        self.practice = 0
        self.backlog = 0
        self.skills = 2
        self.weaknesses = 3


class DailyEvolutionTests(unittest.TestCase):
    def make_engine(self, root: Path, *, fail_growth=False):
        calls = Calls()

        def growth_cycle():
            calls.growth += 1
            if fail_growth and calls.growth == 1:
                raise RuntimeError("synthetic growth failure")
            calls.skills += 1
            return {
                "status": "completed",
                "skills_added": 1,
                "skills_updated": 0,
                "total_skills": calls.skills,
            }

        def growth_status():
            return {
                "skills": calls.skills,
                "verified_examples": 5,
            }

        def practice_cycle():
            calls.practice += 1
            calls.weaknesses = max(0, calls.weaknesses - 1)
            return {
                "status": "completed",
                "promotion": {"promoted": True},
                "evidence_ref": "practice/evidence.json",
            }

        def practice_status():
            return {
                "weaknesses": [{"id": i} for i in range(calls.weaknesses)],
                "practice_queue": [{"id": 1}] if calls.weaknesses else [],
            }

        def backlog_refresh():
            calls.backlog += 1
            return {
                "date": "today",
                "counts": {"todo": 1, "completed": 2},
                "focus": [{"title": "next"}],
            }

        engine = DailyEvolutionEngine(
            growth_cycle=growth_cycle,
            growth_status=growth_status,
            practice_cycle=practice_cycle,
            practice_status=practice_status,
            backlog_refresh=backlog_refresh,
            settings_path=root / "daily.json",
            history_path=root / "daily_history.jsonl",
        )
        return engine, calls

    def test_runs_once_per_local_day(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, calls = self.make_engine(root)
            first = engine.run_if_due(trigger="test")
            second = engine.run_if_due(trigger="test")

            self.assertEqual(first["status"], "completed")
            self.assertTrue(first["ran"])
            self.assertEqual(second["status"], "already_completed_today")
            self.assertFalse(second["ran"])
            self.assertEqual(calls.growth, 1)
            self.assertEqual(calls.practice, 1)
            self.assertEqual(calls.backlog, 1)
            self.assertFalse(engine.status()["due_today"])

    def test_partial_failure_remains_due_and_retries(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, calls = self.make_engine(root, fail_growth=True)
            first = engine.run_if_due(trigger="test")
            self.assertEqual(first["status"], "partial")
            self.assertTrue(engine.status()["due_today"])

            second = engine.run_if_due(trigger="test")
            self.assertEqual(second["status"], "completed")
            self.assertFalse(engine.status()["due_today"])
            self.assertEqual(calls.growth, 2)
            self.assertEqual(calls.practice, 2)

    def test_manual_force_can_rerun_without_changing_auto_daily_rule(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, calls = self.make_engine(root)
            first = engine.run_if_due(trigger="test")
            forced = engine.run_if_due(trigger="manual", force=True)
            normal = engine.run_if_due(trigger="test")

            self.assertEqual(first["status"], "completed")
            self.assertEqual(forced["status"], "completed")
            self.assertEqual(normal["status"], "already_completed_today")
            self.assertEqual(calls.growth, 2)
            self.assertEqual(calls.practice, 2)

    def test_protected_scope_and_daily_budget_are_hard_bounded(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine, _ = self.make_engine(root)
            status = engine.status()
            self.assertTrue(status["enabled"])
            self.assertEqual(status["max_practice_tasks_per_day"], 1)
            self.assertFalse(status["source_self_edit_allowed"])
            self.assertFalse(status["main_merge_allowed"])
            self.assertFalse(status["external_publish_allowed"])
            self.assertFalse(status["paid_actions_allowed"])
            self.assertFalse(status["secret_access_allowed"])
            self.assertFalse(status["production_database_write_allowed"])
            self.assertFalse(status["approval_bypass_allowed"])
            self.assertIn("approval", status["protected_scope"])
            self.assertIn("production_database", status["protected_scope"])


if __name__ == "__main__":
    unittest.main()
