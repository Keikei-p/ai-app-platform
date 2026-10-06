from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class FinalProductizationValidationV2(unittest.TestCase):
    def test_final_contract(self):
        connectors=(ROOT/"src"/"core"/"connectors.py").read_text(encoding="utf-8")
        product=(ROOT/"src"/"core"/"productization.py").read_text(encoding="utf-8")
        html=(ROOT/"webui"/"index.html").read_text(encoding="utf-8")
        self.assertIn("def _test_result",connectors)
        self.assertIn("for_transfer: bool = False",product)
        self.assertIn('data-mobile-view="integrations"',html)
        self.assertIn('data-mobile-view="settings"',html)

if __name__=="__main__":
    unittest.main()
