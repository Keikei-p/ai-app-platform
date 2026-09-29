from __future__ import annotations
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class FinalUsabilityValidation(unittest.TestCase):
    def test_usability_layer_is_present(self):
        html=(ROOT/"webui"/"index.html").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        css=(ROOT/"webui"/"styles.css").read_text(encoding="utf-8")
        self.assertIn("quick-start-grid",html)
        self.assertIn('id="taskProgress"',html)
        self.assertIn("saveDraft",app)
        self.assertIn("setTaskProgress",app)
        self.assertIn("mobile-tabbar",css)

if __name__=="__main__":
    unittest.main()
