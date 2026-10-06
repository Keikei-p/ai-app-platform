from __future__ import annotations
from pathlib import Path
import unittest
import json

ROOT=Path(__file__).resolve().parents[1]

class FinalMultiMissionAttestationValidation(unittest.TestCase):
    def test_multi_mission_attestation_is_source_guarded(self):
        evidence=json.loads((ROOT/"evidence"/"multi_mission_e2e_ci.json").read_text(encoding="utf-8"))
        verifier=(ROOT/"src"/"core"/"multi_mission_e2e.py").read_text(encoding="utf-8")
        self.assertTrue(evidence["verified"])
        self.assertEqual(evidence["ci"]["run_number"],900)
        self.assertTrue(all(evidence["checks"].values()))
        self.assertIn("source_blobs",evidence)
        self.assertIn("current !=",verifier)
        self.assertIn("repository_ci_attestation",verifier)

if __name__=="__main__":
    unittest.main()
