from __future__ import annotations
from pathlib import Path
import unittest
import json

ROOT=Path(__file__).resolve().parents[1]

class FinalCrossModeAttestationValidation(unittest.TestCase):
    def test_repository_attestation_is_present_and_source_guarded(self):
        evidence=json.loads((ROOT/"evidence"/"cross_mode_e2e_ci.json").read_text(encoding="utf-8"))
        verifier=(ROOT/"src"/"core"/"cross_mode_e2e.py").read_text(encoding="utf-8")
        self.assertTrue(evidence["verified"])
        self.assertEqual(set(evidence["modes"]),{"app","web","automation"})
        self.assertEqual(evidence["ci"]["run_number"],889)
        self.assertIn("source_blobs",evidence)
        self.assertIn("current !=",verifier)
        self.assertIn("repository_ci_attestation",verifier)

if __name__=="__main__":
    unittest.main()
