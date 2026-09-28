import tempfile
import unittest
from pathlib import Path

from src.core.candidate_arena import CandidateArena
from src.core.evaluation_engine import EvaluationReport
from src.core.model_benchmark import ModelBenchmarkStore
from src.core.project_memory import ProjectMemory


def evaluation(score, *, tests=True, security=True, design=True, preview=True):
    return EvaluationReport(
        score=score,
        tests_passed=tests,
        test_pass_ratio=1.0 if tests else 0.5,
        design_passed=design,
        design_score=score,
        security_passed=security,
        preview_ready=preview,
        release_ready=False,
        artifact_count=1,
        learning_eligible=tests and security and design and preview,
        regressions=(),
        created_at="2026-01-01T00:00:00+00:00",
    )


class CandidateArenaTests(unittest.TestCase):
    def test_only_improved_non_regressing_candidate_can_win(self):
        arena = CandidateArena()
        report = arena.compare_reports(
            evaluation(85),
            {
                "good": evaluation(94),
                "worse": evaluation(80),
                "broken": evaluation(98, security=False),
            },
        )
        self.assertEqual(report.status, "human_review_required")
        self.assertEqual(report.winner_id, "good")
        self.assertFalse(report.auto_apply)
        broken = next(x for x in report.candidates if x.candidate_id == "broken")
        self.assertFalse(broken.eligible)

    def test_no_candidate_auto_applies(self):
        report = CandidateArena().compare_reports(
            evaluation(90),
            {"same": evaluation(90)},
        )
        self.assertIsNone(report.winner_id)
        self.assertFalse(report.auto_apply)


class MemoryAndBenchmarkTests(unittest.TestCase):
    def test_project_memory_can_filter_verified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = ProjectMemory()
            store.record(root, category="note", statement="draft", verified=False)
            store.record(root, category="verified", statement="works", verified=True)
            rows = store.recent(root, verified_only=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].statement, "works")

    def test_model_benchmark_uses_recorded_outcomes_only(self):
        with tempfile.TemporaryDirectory() as td:
            store = ModelBenchmarkStore(Path(td) / "bench.jsonl")
            store.record(
                capability="coding",
                provider="p1",
                model="m1",
                success=True,
                quality_score=95,
            )
            store.record(
                capability="coding",
                provider="p2",
                model="m2",
                success=False,
                quality_score=70,
            )
            summary = store.summary("coding")
            self.assertEqual(summary["observations"], 2)
            self.assertEqual(summary["models"][0]["model"], "m1")


if __name__ == "__main__":
    unittest.main()
