from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest

from src.core.autonomous_growth import AutonomousGrowthEngine


class FakeLearning:
    def __init__(self, rows):
        self.rows = rows

    def recent(self, limit=1000):
        return self.rows[:limit]

    def stats(self):
        scores = [row.evaluation_score for row in self.rows]
        return {
            "verified_examples": len(self.rows),
            "average_score": sum(scores) / len(scores) if scores else 0,
            "repaired_examples": sum(1 for row in self.rows if getattr(row, "repair_count", 0)),
        }


def example(score=96, instruction="美容室のWebサイトを作る", lesson="モバイル優先で明確なCTAと十分な余白を使う"):
    return SimpleNamespace(
        example_id="ex-" + str(score),
        evaluation_score=score,
        instruction=instruction,
        lesson=lesson,
        quality={
            "tests_passed": True,
            "design_passed": True,
            "security_passed": True,
            "preview_ready": True,
        },
        repair_count=0,
    )


class AutonomousGrowthTests(unittest.TestCase):
    def test_verified_success_becomes_reusable_skill(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = AutonomousGrowthEngine(
                learning=FakeLearning([example()]),
                skills_path=root / "skills.json",
                settings_path=root / "settings.json",
            )
            result = engine.run_cycle()
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["skills_added"], 1)
            self.assertFalse(result["source_code_mutated"])
            self.assertEqual(len(engine.skills()), 1)
            context = engine.context_for("新しいWebサイトを作りたい")
            self.assertTrue(context)
            self.assertIn("モバイル優先", context[0])

    def test_low_quality_example_is_not_promoted(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = AutonomousGrowthEngine(
                learning=FakeLearning([example(score=72)]),
                skills_path=root / "skills.json",
                settings_path=root / "settings.json",
            )
            result = engine.run_cycle()
            self.assertEqual(result["eligible_examples"], 0)
            self.assertEqual(result["total_skills"], 0)


if __name__ == "__main__":
    unittest.main()
