from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GrowthUIContractTests(unittest.TestCase):
    def test_web_ui_exposes_all_conversation_modes(self):
        html = (ROOT / "webui" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "webui" / "app.js").read_text(encoding="utf-8")
        for mode in ("chat", "app", "web", "automation", "ivy_lab"):
            self.assertIn(f'data-mode="{mode}"', html)
        self.assertIn("/api/v1/growth/status", app)
        self.assertIn("/api/v1/growth/run", app)
        self.assertIn("/api/v1/growth/settings", app)
        self.assertIn("mode:state.currentMode", app)
        self.assertIn("放置成長ループ稼働中", app)

    def test_growth_ui_explains_protected_scope(self):
        html = (ROOT / "webui" / "index.html").read_text(encoding="utf-8")
        self.assertIn("Aivy本体ソース", html)
        self.assertIn("main", html)
        self.assertIn("課金", html)
        self.assertIn("本番公開", html)

    def test_develop_contains_safe_background_growth_loop(self):
        growth = (ROOT / "src" / "core" / "autonomous_growth.py").read_text(encoding="utf-8")
        self.assertIn("start_background", growth)
        self.assertIn("allow_source_self_edit", growth)
        self.assertIn("allow_main_merge", growth)
        self.assertIn("allow_paid_actions", growth)


if __name__ == "__main__":
    unittest.main()
