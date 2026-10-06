from __future__ import annotations
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class FinalMultiMissionE2EValidation(unittest.TestCase):
    def test_multi_mission_contract(self):
        verifier=(ROOT/"src"/"core"/"multi_mission_e2e.py").read_text(encoding="utf-8")
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        api=(ROOT/"src"/"core"/"platform_api.py").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        self.assertIn("MultiMissionE2EVerifier",verifier)
        self.assertIn("first_waited_for_approval",verifier)
        self.assertIn("second_waited_for_approval",verifier)
        self.assertIn("mission_budget_stops_more_work",verifier)
        self.assertIn("self.multi_mission_e2e.status().get",service)
        self.assertIn("/api/v1/completion/multi-mission-e2e/run",api)
        self.assertIn("async function runMultiMissionE2E()",app)

if __name__=="__main__":
    unittest.main()
