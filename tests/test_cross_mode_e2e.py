from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from src.core.config import ROOT_DIR
from src.core.cross_mode_e2e import CrossModeE2EVerifier


class CrossModeE2ETests(unittest.TestCase):
    def test_real_app_web_automation_generation_passes_quality_gates(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            verifier = CrossModeE2EVerifier(
                root_dir=ROOT_DIR,
                evidence_path=root / "cross_mode.json",
                attestation_path=root / "missing_attestation.json",
            )
            report = verifier.run()

            self.assertTrue(report["verified"])
            self.assertEqual(report["modes"], ["app", "web", "automation"])
            self.assertFalse(report["external_actions"])
            self.assertFalse(report["credentials_used"])
            self.assertFalse(report["paid_actions"])
            self.assertFalse(report["production_data_written"])
            self.assertEqual(len(report["cases"]), 3)

            by_mode = {row["mode"]: row for row in report["cases"]}
            self.assertEqual(by_mode["app"]["actual_app_type"], "inventory")
            self.assertEqual(by_mode["web"]["actual_app_type"], "booking")
            self.assertEqual(by_mode["automation"]["actual_app_type"], "social_automation")
            for row in by_mode.values():
                self.assertTrue(row["passed"])
                self.assertTrue(row["tests_passed"])
                self.assertTrue(row["design_passed"])
                self.assertTrue(row["security_passed"])
                self.assertTrue(row["preview_ready"])
                self.assertGreater(row["generated_files"], 0)
            self.assertTrue(by_mode["automation"]["social_safe_defaults"])

            status = verifier.status()
            self.assertTrue(status["verified"])
            self.assertEqual(status["source"], "local_runtime_evidence")
            self.assertFalse(status["stale"])

    def test_repository_ci_attestation_matches_current_sources(self):
        with TemporaryDirectory() as tmp:
            verifier = CrossModeE2EVerifier(
                root_dir=ROOT_DIR,
                evidence_path=Path(tmp) / "missing_local.json",
                attestation_path=ROOT_DIR / "evidence" / "cross_mode_e2e_ci.json",
            )
            status = verifier.status()
            self.assertTrue(status["verified"])
            self.assertEqual(status["source"], "repository_ci_attestation")
            self.assertFalse(status["stale"])
            self.assertEqual(
                {row["mode"] for row in status["cases"]},
                {"app", "web", "automation"},
            )

    def test_evidence_becomes_stale_when_source_blob_contract_changes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "cross_mode.json"
            verifier = CrossModeE2EVerifier(
                root_dir=ROOT_DIR,
                evidence_path=evidence,
                attestation_path=root / "missing_attestation.json",
            )
            report = verifier.run()
            self.assertTrue(report["verified"])

            raw = json.loads(evidence.read_text(encoding="utf-8"))
            first = next(iter(raw["source_blobs"]))
            raw["source_blobs"][first] = "0" * 40
            evidence.write_text(json.dumps(raw), encoding="utf-8")

            status = verifier.status()
            self.assertFalse(status["verified"])
            self.assertTrue(status["stale"])


if __name__ == "__main__":
    unittest.main()
