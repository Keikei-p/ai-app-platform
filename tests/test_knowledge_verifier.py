import json
import tempfile
import unittest
from pathlib import Path

from src.core.knowledge_store import VerifiedKnowledgeStore
from src.core.knowledge_verifier import ProjectKnowledgeVerifier


class ProjectKnowledgeVerifierTests(unittest.TestCase):
    def _candidate(self, store):
        item = store.ingest(
            topic="Demo framework",
            statement="This project configuration passed verified checks.",
            source_kind="official_docs",
            source_locator="https://official.example.test/docs",
        )
        return store.promote_candidate(item.knowledge_id)

    def test_missing_project_reports_cannot_verify_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "demo"
            project.mkdir()
            store = VerifiedKnowledgeStore(root / "knowledge.json")
            candidate = self._candidate(store)
            verifier = ProjectKnowledgeVerifier(store, root)
            with self.assertRaises(ValueError):
                verifier.verify(
                    candidate.knowledge_id,
                    project_slug="demo",
                    verifier_types=["tests"],
                )

    def test_real_passing_reports_generate_hashed_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "demo"
            reports = project / ".aiapp" / "reports"
            reports.mkdir(parents=True)
            (reports / "test_report.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
            (reports / "security_report.json").write_text(json.dumps({"passed": True}), encoding="utf-8")
            (project / "design_review.json").write_text(json.dumps({"passed": True, "score": 95}), encoding="utf-8")

            store = VerifiedKnowledgeStore(root / "knowledge.json")
            candidate = self._candidate(store)
            result = ProjectKnowledgeVerifier(store, root).verify(
                candidate.knowledge_id,
                project_slug="demo",
                verifier_types=["tests", "design", "security"],
            )
            self.assertEqual(result.knowledge.trust_level, "verified")
            self.assertEqual(set(result.knowledge.verified_by), {"tests", "design", "security"})
            self.assertEqual(len(result.evidence_refs), 3)
            self.assertTrue(all(":sha256:" in x for x in result.evidence_refs))

    def test_free_form_evidence_cannot_be_injected_through_verifier(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "demo").mkdir()
            store = VerifiedKnowledgeStore(root / "knowledge.json")
            candidate = self._candidate(store)
            verifier = ProjectKnowledgeVerifier(store, root)
            with self.assertRaises(ValueError):
                verifier.verify(
                    candidate.knowledge_id,
                    project_slug="demo",
                    verifier_types=["human_review"],
                )


if __name__ == "__main__":
    unittest.main()
