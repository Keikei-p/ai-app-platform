from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WebUsabilityContractTests(unittest.TestCase):
    def test_home_has_clear_quick_start_choices(self):
        html = (ROOT / "webui" / "index.html").read_text(encoding="utf-8")
        for mode in ("app", "web", "automation", "chat"):
            self.assertIn(f'data-starter-mode="{mode}"', html)
        self.assertIn("アプリを作る", html)
        self.assertIn("サイトを作る", html)
        self.assertIn("自動化する", html)
        self.assertIn("まず相談する", html)

    def test_composer_keeps_modes_progress_and_drafts_visible(self):
        html = (ROOT / "webui" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "webui" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="taskProgress"', html)
        self.assertIn('id="draftStatus"', html)
        self.assertIn("composer-mode-switch", html)
        self.assertIn("function saveDraft()", app)
        self.assertIn("function restoreDraft()", app)
        self.assertIn("function setTaskProgress(", app)
        self.assertIn("stageProgress", app)
        self.assertNotIn("$('#prompt').disabled=value", app)

    def test_resume_and_mobile_navigation_are_wired(self):
        html = (ROOT / "webui" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "webui" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="resumeWork"', html)
        self.assertIn('id="resumeConversation"', html)
        self.assertIn('id="resumeProject"', html)
        for view in ("home", "projects", "lab", "settings"):
            self.assertIn(f'data-mobile-view="{view}"', html)
        self.assertIn("function renderResume()", app)
        self.assertIn("aivy-last-thread", app)
        self.assertIn("mobileNewChat", app)

    def test_usability_css_has_mobile_tabbar_and_panel_surface(self):
        css = (ROOT / "webui" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("--panel:", css)
        self.assertIn(".mobile-tabbar", css)
        self.assertIn(".quick-start-grid", css)
        self.assertIn(".task-progress", css)
        self.assertIn(".toast-region", css)


if __name__ == "__main__":
    unittest.main()
