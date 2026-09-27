import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.core.evaluation_engine import EvaluationReport
from src.core.evolution_engine import VerifiedEvolutionEngine
from src.core.evolution_experiments import EvolutionExperimentStore


def report(score):
    return EvaluationReport(
        score=score,
        tests_passed=True,
        test_pass_ratio=1.0,
        design_passed=True,
        design_score=score,
        security_passed=True,
        preview_ready=True,
        release_ready=False,
        artifact_count=1,
        learning_eligible=True,
        regressions=(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


class EvolutionExperimentStoreTests(unittest.TestCase):
    def test_eligible_candidate_is_persisted_for_human_review(self):
        with tempfile.TemporaryDirectory() as td:
            engine = VerifiedEvolutionEngine()
            decision = engine.compare(
                report(90),
                report(95),
                changed_paths=["src/core/generator.py"],
                evidence_refs=["ci:123"],
            )
            store = EvolutionExperimentStore(Path(td) / "experiments.json")
            item = store.create(
                title="Improve generator",
                baseline_label="current",
                candidate_label="candidate-a",
                changed_paths=["src/core/generator.py"],
                evidence_refs=["ci:123"],
                decision=decision,
            )
            self.assertEqual(item.status, "human_review_required")
            self.assertEqual(store.get(item.experiment_id).candidate_label, "candidate-a")

    def test_human_review_changes_status_but_does_not_apply_anything(self):
        with tempfile.TemporaryDirectory() as td:
            engine = VerifiedEvolutionEngine()
            decision = engine.compare(
                report(90),
                report(96),
                changed_paths=["src/core/generator.py"],
                evidence_refs=["ci:456"],
            )
            store = EvolutionExperimentStore(Path(td) / "experiments.json")
            item = store.create(
                title="Candidate",
                baseline_label="baseline",
                candidate_label="candidate",
                changed_paths=["src/core/generator.py"],
                evidence_refs=["ci:456"],
                decision=decision,
            )
            reviewed = store.record_human_review(item.experiment_id, approved=True, note="reviewed")
            self.assertEqual(reviewed.status, "human_approved")
            self.assertTrue(reviewed.decision["human_review"]["approved"])

    def test_rejected_candidate_cannot_be_human_approved(self):
        with tempfile.TemporaryDirectory() as td:
            engine = VerifiedEvolutionEngine()
            decision = engine.compare(
                report(90),
                report(89),
                changed_paths=["src/core/generator.py"],
                evidence_refs=["ci:789"],
            )
            store = EvolutionExperimentStore(Path(td) / "experiments.json")
            item = store.create(
                title="Worse candidate",
                baseline_label="baseline",
                candidate_label="candidate",
                changed_paths=["src/core/generator.py"],
                evidence_refs=["ci:789"],
                decision=decision,
            )
            with self.assertRaises(ValueError):
                store.record_human_review(item.experiment_id, approved=True)


if __name__ == "__main__":
    unittest.main()
