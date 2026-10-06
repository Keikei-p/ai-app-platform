from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CompletionReadinessUIContractTests(unittest.TestCase):
    def test_api_exposes_completion_readiness(self):
        api = (ROOT / "src" / "core" / "platform_api.py").read_text(encoding="utf-8")
        service = (ROOT / "src" / "core" / "platform_service.py").read_text(encoding="utf-8")
        self.assertIn('"/api/v1/completion/readiness"', api)
        self.assertIn("CompletionReadinessEngine", service)
        self.assertIn("def completion_readiness_status", service)

    def test_completion_evidence_uses_real_cross_mode_and_multi_mission_verifiers(self):
        service = (ROOT / "src" / "core" / "platform_service.py").read_text(encoding="utf-8")
        self.assertIn("CrossModeE2EVerifier", service)
        self.assertIn("MultiMissionE2EVerifier", service)
        self.assertIn('"cross_mode_real_app_e2e_verified": bool(self.cross_mode_e2e.status().get("verified"))', service)
        self.assertIn('"multi_mission_end_to_end_verified": bool(self.multi_mission_e2e.status().get("verified"))', service)
        self.assertIn("LongRunSoakMonitor", service)
        self.assertIn('"long_run_soak_verified": bool(self.long_run_soak.status().get("verified"))', service)
        self.assertIn("self.long_run_soak.start_background()", service)
        self.assertIn("CloudRuntimeReadinessVerifier", service)
        self.assertIn('"cloud_runtime_ready": bool(self.cloud_runtime.status().get("verified"))', service)
        self.assertIn("self.cloud_runtime.run()", service)

    def test_ivy_lab_shows_completion_score_and_highest_gap(self):
        html = (ROOT / "webui" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "webui" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "webui" / "styles.css").read_text(encoding="utf-8")
        for token in (
            'id="completionHeadline"',
            'id="completionScore"',
            'id="completionBar"',
            'id="completionGap"',
            'id="completionCriteria"',
            'id="runCrossModeE2E"',
            'id="runMultiMissionE2E"',
            'id="refreshCompletion"',
            'id="completionEvidence"',
            'id="checkpointSoak"',
            'id="soakStatus"',
            'id="soakBar"',
            'id="soakSummary"',
        ):
            self.assertIn(token, html)
        self.assertIn("/api/v1/completion/readiness", app)
        self.assertIn("/api/v1/completion/cross-mode-e2e", app)
        self.assertIn("/api/v1/completion/multi-mission-e2e", app)
        self.assertIn("/api/v1/completion/soak", app)
        self.assertIn("highest_priority_gap", app)
        self.assertIn("async function runCrossModeE2E()", app)
        self.assertIn("async function runMultiMissionE2E()", app)
        self.assertIn("async function checkpointSoak()", app)
        self.assertIn("async function refreshCompletion()", app)
        self.assertIn(".completion-readiness-card", css)


if __name__ == "__main__":
    unittest.main()
