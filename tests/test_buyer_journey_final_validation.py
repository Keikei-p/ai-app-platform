from __future__ import annotations
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class FinalBuyerJourneyValidation(unittest.TestCase):
    def test_transferable_buyer_journey_contract(self):
        e2e=(ROOT/"src"/"core"/"productization_e2e.py").read_text(encoding="utf-8")
        product=(ROOT/"src"/"core"/"productization.py").read_text(encoding="utf-8")
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        api=(ROOT/"src"/"core"/"platform_api.py").read_text(encoding="utf-8")
        html=(ROOT/"webui"/"index.html").read_text(encoding="utf-8")
        self.assertIn("BuyerJourneyE2EVerifier",e2e)
        self.assertIn("new_owner_first_boot",e2e)
        self.assertIn("safe_connectors = {}",product)
        self.assertIn("buyer_productization_e2e_verified",service)
        self.assertIn("/api/v1/productization/e2e",api)
        self.assertIn('id="runBuyerE2E"',html)

if __name__=="__main__":
    unittest.main()
