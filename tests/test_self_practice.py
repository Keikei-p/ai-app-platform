from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from src.core.autonomous_growth import AutonomousGrowthEngine
from src.core.candidate_arena import CandidateArena
from src.core.model_benchmark import ModelBenchmarkStore
from src.core.self_practice import SelfPracticeEngine, WeaknessDetector


class FakeLearning:
    def __init__(self, rows):
        self.rows = list(rows)

    def recent(self, limit=1000):
        return self.rows[:limit]

    def stats(self):
        scores = [int(x.evaluation_score) for x in self.rows]
        return {
            "verified_examples": len(self.rows),
            "average_score": sum(scores) / len(scores) if scores else 0.0,
            "repaired_examples": sum(1 for x in self.rows if int(getattr(x, "repair_count", 0)) > 0),
        }


def example(
    example_id="ex-1",
    *,
    score=96,
    instruction="営業管理アプリを作る",
    repair_count=0,
):
    return SimpleNamespace(
        example_id=example_id,
        evaluation_score=score,
        instruction=instruction,
        lesson="Tests Design Security Previewを独立Evidenceで確認する",
        quality={
            "tests_passed": True,
            "design_passed": True,
            "security_passed": True,
            "preview_ready": True,
        },
        repair_count=repair_count,
    )


class SelfPracticeTests(unittest.TestCase):
    def test_detector_finds_sparse_verified_experience(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            detector = WeaknessDetector(
                FakeLearning([example()]),
                ModelBenchmarkStore(root / "bench.jsonl"),
                root / "workspace",
            )
            rows = detector.detect()
            self.assertTrue(any(x.kind == "training_data_scarcity" for x in rows))
            self.assertTrue(any(x.kind == "mode_experience" for x in rows))

    def test_one_synthetic_practice_can_promote_verified_skill(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            learning = FakeLearning([example()])
            growth = AutonomousGrowthEngine(
                learning=learning,
                skills_path=root / "skills.json",
                settings_path=root / "growth.json",
            )
            engine = SelfPracticeEngine(
                learning=learning,
                benchmark=ModelBenchmarkStore(root / "bench.jsonl"),
                arena=CandidateArena(),
                promote_skill=growth.promote_practice_skill,
                history_path=root / "practice.jsonl",
                workspace_dir=root / "workspace",
                evidence_dir=root / "practice_evidence",
            )

            result = engine.run_one()

            self.assertEqual(result["status"], "completed")
            self.assertTrue(result["practice"]["synthetic_only"])
            self.assertFalse(result["practice"]["network_used"])
            self.assertFalse(result["practice"]["paid_actions_used"])
            self.assertFalse(result["practice"]["production_data_used"])
            self.assertFalse(result["practice"]["source_code_mutated"])
            self.assertTrue(result["practice"]["dimension_review"]["all_passed"])
            self.assertTrue(result["promotion"]["promoted"])
            self.assertEqual(len(growth.skills()), 1)
            self.assertTrue((root / result["evidence_ref"]).is_file())

    def test_practice_queue_advances_after_promotion(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            learning = FakeLearning([example()])
            growth = AutonomousGrowthEngine(
                learning=learning,
                skills_path=root / "skills.json",
                settings_path=root / "growth.json",
            )
            engine = SelfPracticeEngine(
                learning=learning,
                benchmark=ModelBenchmarkStore(root / "bench.jsonl"),
                arena=CandidateArena(),
                promote_skill=growth.promote_practice_skill,
                history_path=root / "practice.jsonl",
                workspace_dir=root / "workspace",
                evidence_dir=root / "practice_evidence",
            )
            first = engine.run_one()
            second = engine.run_one()
            self.assertTrue(first["promotion"]["promoted"])
            self.assertTrue(second["promotion"]["promoted"])
            first_task = first["practice"]["task"]["task_id"]
            second_task = second["practice"]["task"]["task_id"]
            self.assertNotEqual(first_task, second_task)
            self.assertEqual(len(growth.skills()), 2)

    def test_guardian_reports_become_evidence_backed_weaknesses(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "workspace" / "demo" / ".aiapp" / "reports"
            reports.mkdir(parents=True)
            (reports / "accessibility_guardian.json").write_text(
                '{"status":"blocked","issues":[{"severity":"high","rule":"label"}]}',
                encoding="utf-8",
            )
            detector = WeaknessDetector(
                FakeLearning([example() for _ in range(8)]),
                ModelBenchmarkStore(root / "bench.jsonl"),
                root / "workspace",
            )
            rows = detector.detect()
            accessibility = [x for x in rows if x.kind == "accessibility"]
            self.assertTrue(accessibility)
            self.assertTrue(accessibility[0].evidence_refs)
            self.assertIn("accessibility_guardian.json", accessibility[0].evidence_refs[0])

    def test_promotion_rejects_low_score_or_missing_evidence(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            growth = AutonomousGrowthEngine(
                learning=FakeLearning([]),
                skills_path=root / "skills.json",
                settings_path=root / "growth.json",
            )
            low = growth.promote_practice_skill(
                mode="web",
                title="practice",
                lesson="safe lesson",
                score=89,
                evidence_ref="evidence.json",
                source_id="practice:test",
            )
            missing = growth.promote_practice_skill(
                mode="web",
                title="practice",
                lesson="safe lesson",
                score=96,
                evidence_ref="",
                source_id="practice:test",
            )
            self.assertFalse(low["promoted"])
            self.assertFalse(missing["promoted"])
            self.assertEqual(growth.skills(), [])

    def test_status_exposes_bounded_compute_and_protected_scope(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = SelfPracticeEngine(
                learning=FakeLearning([]),
                benchmark=ModelBenchmarkStore(root / "bench.jsonl"),
                arena=CandidateArena(),
                history_path=root / "practice.jsonl",
                workspace_dir=root / "workspace",
                evidence_dir=root / "practice_evidence",
            )
            status = engine.status()
            self.assertEqual(status["max_tasks_per_cycle"], 1)
            self.assertEqual(status["compute_budget"]["max_parallel_tasks"], 1)
            self.assertFalse(status["network_allowed"])
            self.assertFalse(status["paid_actions_allowed"])
            self.assertFalse(status["production_access_allowed"])
            self.assertFalse(status["source_self_edit_allowed"])
            self.assertIn("main_branch", status["protected_scope"])
            self.assertIn("production_database", status["protected_scope"])


if __name__ == "__main__":
    unittest.main()
