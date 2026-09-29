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

    def test_growth_api_and_protected_scope_are_present(self):
        api = (ROOT / "src" / "core" / "platform_api.py").read_text(encoding="utf-8")
        growth = (ROOT / "src" / "core" / "autonomous_growth.py").read_text(encoding="utf-8")
        service = (ROOT / "src" / "core" / "platform_service.py").read_text(encoding="utf-8")
        self.assertIn("/api/v1/growth/status", api)
        self.assertIn("/api/v1/growth/run", api)
        self.assertIn("start_background", growth)
        self.assertIn('"allow_source_self_edit": False', growth)
        self.assertIn('"allow_main_merge": False', growth)
        self.assertIn('"allow_paid_actions": False', growth)
        self.assertIn("self.autonomous_growth.start_background()", service)

    def test_modes_have_distinct_generation_standards(self):
        chat = (ROOT / "src" / "core" / "chat_partner.py").read_text(encoding="utf-8")
        self.assertIn("WEB MODE:", chat)
        self.assertIn("AUTOMATION MODE:", chat)
        self.assertIn("APP MODE:", chat)
        self.assertIn("SEO", chat)
        self.assertIn("重複実行防止", chat)
        self.assertIn("認証・権限", chat)


if __name__ == "__main__":
    unittest.main()
