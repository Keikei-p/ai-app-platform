from __future__ import annotations
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class FinalLongRunSoakValidation(unittest.TestCase):
    def test_real_soak_contract_is_strict(self):
        soak=(ROOT/"src"/"core"/"long_run_soak.py").read_text(encoding="utf-8")
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        api=(ROOT/"src"/"core"/"platform_api.py").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        self.assertIn("TARGET_SECONDS = 24 * 60 * 60",soak)
        self.assertIn("HEARTBEAT_SECONDS = 15 * 60",soak)
        self.assertIn("MAX_GAP_SECONDS = 45 * 60",soak)
        self.assertIn("MIN_SAMPLES = 80",soak)
        self.assertIn("self.long_run_soak.start_background()",service)
        self.assertIn("/api/v1/completion/soak/checkpoint",api)
        self.assertIn("async function checkpointSoak()",app)

if __name__=="__main__":
    unittest.main()
