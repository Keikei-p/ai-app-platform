import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.core.evaluation_engine import EvaluationReport
from src.core.evolution_engine import VerifiedEvolutionEngine
from src.core.root_policy_guard import RootPolicyGuard


def report(score=95):
    return EvaluationReport(
        score=score,
        tests_passed=True,
        test_pass_ratio=1.0,
        design_passed=True,
        design_score=95,
        security_passed=True,
        preview_ready=True,
        release_ready=False,
        artifact_count=1,
        learning_eligible=True,
        regressions=(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


class RootPolicyGuardTests(unittest.TestCase):
    def _write(self, root: Path, rel: str, text: str):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_actual_safety_change_is_detected_even_when_not_declared(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            base = Path(a); cand = Path(b)
            self._write(base, "src/core/safety.py", "SAFE = True\n")
            self._write(cand, "src/core/safety.py", "SAFE = False\n")
            diff = RootPolicyGuard().compare(base, cand)
            self.assertFalse(diff.intact)
            self.assertIn("src/core/safety.py", diff.changed_paths)

    def test_added_workflow_is_protected_change(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            base = Path(a); cand = Path(b)
            self._write(cand, ".github/workflows/bypass.yml", "name: bypass\n")
            diff = RootPolicyGuard().compare(base, cand)
            self.assertIn(".github/workflows/bypass.yml", diff.added_in_candidate)

    def test_verified_evolution_tree_comparison_cannot_hide_policy_change(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            base = Path(a); cand = Path(b)
            self._write(base, "src/core/safety.py", "SAFE = True\n")
            self._write(cand, "src/core/safety.py", "SAFE = False\n")
            engine = VerifiedEvolutionEngine()
            decision = engine.compare_verified_trees(
                report(90),
                report(98),
                baseline_root=base,
                candidate_root=cand,
                changed_paths=["src/core/generator.py"],
                evidence_refs=["ci:pass"],
            )
            self.assertFalse(decision.eligible)
            self.assertIn("src/core/safety.py", decision.protected_changes)


if __name__ == "__main__":
    unittest.main()
