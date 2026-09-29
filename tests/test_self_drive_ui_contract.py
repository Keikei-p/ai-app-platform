from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SelfDriveUIContractTests(unittest.TestCase):
    def test_api_exposes_self_drive_status_run_and_settings(self):
        api = (ROOT / "src" / "core" / "platform_api.py").read_text(encoding="utf-8")
        self.assertIn('"/api/v1/self-drive/status"', api)
        self.assertIn('"/api/v1/self-drive/run"', api)
        self.assertIn('"/api/v1/self-drive/settings"', api)

    def test_platform_wires_self_drive_without_auto_approval(self):
        service = (ROOT / "src" / "core" / "platform_service.py").read_text(encoding="utf-8")
        self.assertIn("SelfDriveEngine", service)
        self.assertIn("self.self_drive.start_background()", service)
        self.assertIn("approved_build=False", service)
        self.assertIn("self_drive_scheduler", service)
        self.assertIn("self_drive_approval_boundary", service)

    def test_ivy_lab_shows_autopilot_controls_and_queue(self):
        html = (ROOT / "webui" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "webui" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "webui" / "styles.css").read_text(encoding="utf-8")
        for token in (
            'id="toggleSelfDrive"',
            'id="runSelfDrive"',
            'id="selfDriveQueue"',
            'id="selfDriveApproval"',
            'id="selfDriveLast"',
        ):
            self.assertIn(token, html)
        self.assertIn("/api/v1/self-drive/status", app)
        self.assertIn("/api/v1/self-drive/run", app)
        self.assertIn("/api/v1/self-drive/settings", app)
        self.assertIn("async function runSelfDrive()", app)
        self.assertIn(".self-drive-dashboard", css)

    def test_multi_element_handlers_use_query_selector_all(self):
        app = (ROOT / "webui" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("$('[data-prompt]').forEach", app)
        self.assertNotIn("$('[data-mode]').forEach", app)
        self.assertNotIn("$('[data-starter-mode]').forEach", app)
        self.assertNotIn("$('.nav-item[data-view]').forEach", app)
        self.assertNotIn("$('[data-mobile-view]').forEach", app)


if __name__ == "__main__":
    unittest.main()
