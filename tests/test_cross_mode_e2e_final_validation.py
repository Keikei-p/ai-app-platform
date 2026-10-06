from __future__ import annotations
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class FinalCrossModeE2EValidation(unittest.TestCase):
    def test_cross_mode_e2e_contract(self):
        verifier=(ROOT/"src"/"core"/"cross_mode_e2e.py").read_text(encoding="utf-8")
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        api=(ROOT/"src"/"core"/"platform_api.py").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        self.assertIn("CrossModeE2EVerifier",verifier)
        self.assertIn('"mode": "app"',verifier)
        self.assertIn('"mode": "web"',verifier)
        self.assertIn('"mode": "automation"',verifier)
        self.assertIn("TemporaryDirectory",verifier)
        self.assertIn("self.cross_mode_e2e.status().get",service)
        self.assertIn("/api/v1/completion/cross-mode-e2e/run",api)
        self.assertIn("async function runCrossModeE2E()",app)

if __name__=="__main__":
    unittest.main()
