import json
import tempfile
import unittest
from pathlib import Path

from src.core.completion_certificate import DevelopmentCertificateBuilder


class DevelopmentCertificateTests(unittest.TestCase):
    def _json(self, root: Path, rel: str, data):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def _passing_project(self, root: Path):
        self._json(root, ".aiapp/reports/test_report.json", {"passed": True})
        self._json(root, ".aiapp/reports/security_report.json", {"passed": True})
        self._json(root, "design_review.json", {"passed": True, "score": 95})
        self._json(root, ".aiapp/reports/build_readiness.json", {"preview_ready": True})
        self._json(root, ".aiapp/reports/agent_evaluation.json", {"score": 95})
        self._json(root, ".aiapp/reports/release_manager.json", {
            "all_requested_artifacts_ready": False,
            "targets": [{"target": "web"}],
        })
        trace = self._json(root, ".aiapp/agent/runs/run-1-build.json", {"status": "verified"})
        ledger = root / ".aiapp/agent/evidence.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text('{"status":"pass"}\n', encoding="utf-8")
        return trace.relative_to(root).as_posix()

    def test_verified_preview_certificate_requires_independent_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trace = self._passing_project(root)
            builder = DevelopmentCertificateBuilder()
            cert = builder.create(
                root,
                run_id="run-1",
                project_slug="demo",
                execution_trace_path=trace,
                agent_completion={"complete": True},
            )
            self.assertEqual(cert.status, "verified_preview_candidate")
            self.assertTrue(cert.preview_verified)
            self.assertEqual(cert.external_actions, "approval_required")
            self.assertGreaterEqual(len(cert.evidence), 6)
            saved = builder.save(root, cert)
            self.assertTrue(saved.is_file())

    def test_missing_security_evidence_blocks_certificate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trace = self._passing_project(root)
            (root / ".aiapp/reports/security_report.json").unlink()
            cert = DevelopmentCertificateBuilder().create(
                root,
                run_id="run-1",
                project_slug="demo",
                execution_trace_path=trace,
                agent_completion={"complete": True},
            )
            self.assertEqual(cert.status, "blocked")
            self.assertFalse(cert.preview_verified)
            self.assertTrue(any("security" in x for x in cert.blockers))

    def test_saved_certificate_detects_tampered_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trace = self._passing_project(root)
            builder = DevelopmentCertificateBuilder()
            cert = builder.create(
                root,
                run_id="run-1",
                project_slug="demo",
                execution_trace_path=trace,
                agent_completion={"complete": True},
            )
            builder.save(root, cert)
            self.assertTrue(builder.verify_saved(root).valid)

            (root / ".aiapp/reports/security_report.json").write_text(
                json.dumps({"passed": False}),
                encoding="utf-8",
            )
            integrity = builder.verify_saved(root)
            self.assertFalse(integrity.valid)
            self.assertIn(".aiapp/reports/security_report.json", integrity.mismatched)

    def test_later_agent_ledger_append_does_not_invalidate_certificate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trace = self._passing_project(root)
            builder = DevelopmentCertificateBuilder()
            cert = builder.create(
                root,
                run_id="run-1",
                project_slug="demo",
                execution_trace_path=trace,
                agent_completion={"complete": True},
            )
            builder.save(root, cert)
            ledger = root / ".aiapp/agent/evidence.jsonl"
            with ledger.open("a", encoding="utf-8") as handle:
                handle.write('{"run_id":"later-run","status":"pass"}\n')
            self.assertTrue(builder.verify_saved(root).valid)

    def test_release_ready_still_requires_external_approval(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trace = self._passing_project(root)
            self._json(root, ".aiapp/reports/release_manager.json", {
                "all_requested_artifacts_ready": True,
                "targets": [{"target": "web", "artifact_status": "portable_bundle"}],
            })
            cert = DevelopmentCertificateBuilder().create(
                root,
                run_id="run-1",
                project_slug="demo",
                execution_trace_path=trace,
                agent_completion={"complete": True},
            )
            self.assertEqual(cert.status, "verified_release_candidate")
            self.assertTrue(cert.release_artifacts_verified)
            self.assertEqual(cert.external_actions, "approval_required")


if __name__ == "__main__":
    unittest.main()
