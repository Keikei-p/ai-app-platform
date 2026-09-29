from __future__ import annotations
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class FinalUsabilityValidationV2(unittest.TestCase):
    def test_latest_develop_usability_contract(self):
        html=(ROOT/"webui"/"index.html").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        css=(ROOT/"webui"/"styles.css").read_text(encoding="utf-8")
        for token in ("quick-start-grid","taskProgress","mobile-tabbar","resumeWork"):
            self.assertTrue(token in html or token in css)
        self.assertIn("function saveDraft()",app)
        self.assertIn("function setTaskProgress(",app)
        self.assertIn("--panel:#222226",css)

if __name__=="__main__":
    unittest.main()
