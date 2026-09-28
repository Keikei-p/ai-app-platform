import tempfile
import unittest
from pathlib import Path

from src.core.learning_flywheel import AivyLearningFlywheel


def good_evaluation():
    return {
        "score": 97,
        "tests_passed": True,
        "test_pass_ratio": 1.0,
        "design_passed": True,
        "design_score": 96,
        "security_passed": True,
        "preview_ready": True,
        "release_ready": False,
        "artifact_count": 1,
        "learning_eligible": True,
    }


class AivyLearningFlywheelTests(unittest.TestCase):
    def test_only_verified_success_becomes_learning_example(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir()
            source = project / "app.py"
            source.write_text("print('ok')\n", encoding="utf-8")
            secret = project / ".env"
            secret.write_text("SECRET=value\n", encoding="utf-8")
            store = AivyLearningFlywheel(root / "learning.jsonl")

            result = store.capture_verified_build(
                project_slug="demo",
                instruction="Build a verified demo app",
                outcome_summary="Verified app build completed.",
                result_ok=True,
                evaluation=good_evaluation(),
                evidence_refs=[".aiapp/development_certificate.json"],
                project_dir=project,
                result_files=[source, secret],
                model_route={
                    "mode": "capability_route",
                    "provider": "openai",
                    "model": "coding-model",
                    "capability": "coding",
                },
                ai_status="applied",
                repair_attempts=[],
            )

            self.assertTrue(result["captured"])
            self.assertFalse(result["duplicate"])
            example = result["example"]
            self.assertEqual(example["evaluation_score"], 97)
            self.assertEqual(example["model_route"]["provider"], "openai")
            self.assertEqual([x["path"] for x in example["source_manifest"]], ["app.py"])
            self.assertEqual(store.stats()["verified_examples"], 1)
            self.assertEqual(len(store.supervision_candidates()), 1)

    def test_failed_or_unverified_build_is_never_learned(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir()
            store = AivyLearningFlywheel(root / "learning.jsonl")

            failed = store.capture_verified_build(
                project_slug="demo",
                instruction="broken",
                outcome_summary="failed",
                result_ok=False,
                evaluation=good_evaluation(),
                evidence_refs=["evidence.json"],
                project_dir=project,
            )
            self.assertFalse(failed["captured"])

            not_eligible = good_evaluation()
            not_eligible["learning_eligible"] = False
            rejected = store.capture_verified_build(
                project_slug="demo",
                instruction="not verified",
                outcome_summary="not verified",
                result_ok=True,
                evaluation=not_eligible,
                evidence_refs=["evidence.json"],
                project_dir=project,
            )
            self.assertFalse(rejected["captured"])
            self.assertEqual(store.stats()["verified_examples"], 0)

    def test_same_verified_evidence_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project"
            project.mkdir()
            source = project / "index.html"
            source.write_text("<h1>Aivy</h1>", encoding="utf-8")
            store = AivyLearningFlywheel(root / "learning.jsonl")
            kwargs = dict(
                project_slug="demo",
                instruction="same task",
                outcome_summary="same outcome",
                result_ok=True,
                evaluation=good_evaluation(),
                evidence_refs=["certificate.json"],
                project_dir=project,
                result_files=[source],
            )
            first = store.capture_verified_build(**kwargs)
            second = store.capture_verified_build(**kwargs)
            self.assertTrue(first["captured"])
            self.assertTrue(second["captured"])
            self.assertTrue(second["duplicate"])
            self.assertEqual(store.stats()["verified_examples"], 1)


if __name__ == "__main__":
    unittest.main()
