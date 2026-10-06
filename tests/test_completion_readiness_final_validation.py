from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FinalCompletionReadinessValidation(unittest.TestCase):
    def test_completion_readiness_contract(self):
        engine=(ROOT/"src"/"core"/"completion_readiness.py").read_text(encoding="utf-8")
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        api=(ROOT/"src"/"core"/"platform_api.py").read_text(encoding="utf-8")
        app=(ROOT/"webui"/"app.js").read_text(encoding="utf-8")
        html=(ROOT/"webui"/"index.html").read_text(encoding="utf-8")
        self.assertIn("CompletionReadinessEngine",engine)
        self.assertIn("cross-mode real E2E",engine)
        self.assertIn("multi-mission E2E",engine)
        self.assertIn("24h soak evidence",engine)
        self.assertIn('"cloud_runtime_ready": False',service)
        self.assertIn("/api/v1/completion/readiness",api)
        self.assertIn("highest_priority_gap",app)
        self.assertIn("COMPLETION READINESS",html)


if __name__=="__main__":
    unittest.main()
