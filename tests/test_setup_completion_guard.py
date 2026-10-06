from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.platform_service import PlatformService
from src.core.productization import SetupStateStore


class _FakeConnectors:
    def __init__(self, rows):
        self.rows = dict(rows)

    def get_public(self, connector_id: str):
        if connector_id not in self.rows:
            raise KeyError(connector_id)
        return dict(self.rows[connector_id])


class SetupCompletionGuardTests(unittest.TestCase):
    def make_service(self, root: Path, rows):
        service = PlatformService.__new__(PlatformService)
        service.setup_state = SetupStateStore(root / "setup.json")
        service.connectors = _FakeConnectors(rows)
        return service

    def test_selected_connector_must_be_connected_before_completion(self):
        with TemporaryDirectory() as tmp:
            service = self.make_service(
                Path(tmp),
                {
                    "github": {
                        "name": "GitHub",
                        "status": "setting_incomplete",
                    },
                },
            )
            with self.assertRaisesRegex(ValueError, "接続テスト"):
                service.update_setup({
                    "completed": True,
                    "github_choice": "github",
                })
            self.assertFalse(service.setup_state.get()["completed"])

    def test_connected_selected_connectors_allow_completion(self):
        with TemporaryDirectory() as tmp:
            service = self.make_service(
                Path(tmp),
                {
                    "ollama": {"name": "Ollama", "status": "connected"},
                    "github": {"name": "GitHub", "status": "connected"},
                },
            )
            result = service.update_setup({
                "completed": True,
                "ai_choice": "ollama",
                "github_choice": "github",
            })
            self.assertTrue(result["completed"])

    def test_no_external_selection_can_finish_minimal_local_setup(self):
        with TemporaryDirectory() as tmp:
            service = self.make_service(Path(tmp), {})
            result = service.update_setup({
                "completed": True,
                "ai_choice": "",
                "github_choice": "",
                "cloud_choice": "",
            })
            self.assertTrue(result["completed"])


if __name__ == "__main__":
    unittest.main()
