from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from src.core.config import ROOT_DIR
from src.core.multi_mission_e2e import MultiMissionE2EVerifier


class MultiMissionE2ETests(unittest.TestCase):
    def test_two_missions_advance_only_after_explicit_approval_boundaries(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            verifier = MultiMissionE2EVerifier(
                root_dir=ROOT_DIR,
                evidence_path=root / "multi_mission.json",
                attestation_path=root / "missing_attestation.json",
            )
            report = verifier.run()

            self.assertTrue(report["verified"])
            self.assertEqual(len(report["mission_ids"]), 2)
            self.assertEqual(report["missions_created"], 2)
            self.assertTrue(report["approval_boundary_observed"])
            self.assertFalse(report["external_actions"])
            self.assertFalse(report["credentials_used"])
            self.assertFalse(report["paid_actions"])
            self.assertFalse(report["production_data_written"])
            self.assertTrue(all(report["checks"].values()))
            self.assertEqual(len(report["completed_mission_ids"]), 2)

            status = verifier.status()
            self.assertTrue(status["verified"])
            self.assertEqual(status["source"], "local_runtime_evidence")
            self.assertFalse(status["stale"])

    def test_repository_ci_attestation_matches_current_sources(self):
        with TemporaryDirectory() as tmp:
            verifier = MultiMissionE2EVerifier(
                root_dir=ROOT_DIR,
                evidence_path=Path(tmp) / "missing_local.json",
                attestation_path=ROOT_DIR / "evidence" / "multi_mission_e2e_ci.json",
            )
            status = verifier.status()
            self.assertTrue(status["verified"])
            self.assertEqual(status["source"], "repository_ci_attestation")
            self.assertFalse(status["stale"])
            self.assertTrue(status["checks"]["first_waited_for_approval"])
            self.assertTrue(status["checks"]["second_waited_for_approval"])

    def test_multi_mission_evidence_is_invalidated_by_source_change(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "multi_mission.json"
            verifier = MultiMissionE2EVerifier(
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
