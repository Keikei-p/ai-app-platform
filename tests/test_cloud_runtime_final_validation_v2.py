from __future__ import annotations
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class FinalCloudRuntimeValidationV2(unittest.TestCase):
    def test_guarded_cloud_runtime_contract(self):
        remote=(ROOT/"src"/"core"/"remote_access.py").read_text(encoding="utf-8")
        api=(ROOT/"src"/"core"/"platform_api.py").read_text(encoding="utf-8")
        security=(ROOT/"src"/"tools"/"security_selfcheck.py").read_text(encoding="utf-8")
        self.assertIn("AI_APP_ENABLE_REMOTE",remote)
        self.assertIn("AI_APP_LOCAL_API_TOKEN",remote)
        self.assertIn("bearer_token_required",api)
        self.assertIn("remote_bind_policy",security)
        self.assertIn("guarded remote access policy",security)

if __name__=="__main__":
    unittest.main()
