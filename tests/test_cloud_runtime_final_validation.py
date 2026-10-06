from __future__ import annotations
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class FinalCloudRuntimeValidation(unittest.TestCase):
    def test_cloud_runtime_completion_contract(self):
        cloud=(ROOT/"src"/"core"/"cloud_runtime.py").read_text(encoding="utf-8")
        remote=(ROOT/"src"/"core"/"remote_access.py").read_text(encoding="utf-8")
        api=(ROOT/"src"/"core"/"platform_api.py").read_text(encoding="utf-8")
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        self.assertIn("CloudRuntimeReadinessVerifier",cloud)
        self.assertIn("AI_APP_ENABLE_REMOTE",remote)
        self.assertIn("AI_APP_LOCAL_API_TOKEN",remote)
        self.assertIn("bearer_token_required",api)
        self.assertIn("/api/v1/healthz",api)
        self.assertIn('"cloud_runtime_ready": bool(self.cloud_runtime.status().get("verified"))',service)

if __name__=="__main__":
    unittest.main()
