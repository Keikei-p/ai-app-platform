from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
class FinalCloudRuntimeValidationV3(unittest.TestCase):
    def test_contract(self):
        service=(ROOT/"src"/"core"/"platform_service.py").read_text(encoding="utf-8")
        tests=(ROOT/"tests"/"test_completion_readiness_ui_contract.py").read_text(encoding="utf-8")
        self.assertIn("CloudRuntimeReadinessVerifier",service)
        self.assertIn('"cloud_runtime_ready": bool(self.cloud_runtime.status().get("verified"))',service)
        self.assertNotIn('"cloud_runtime_ready": False',tests)
if __name__=="__main__":
    unittest.main()
