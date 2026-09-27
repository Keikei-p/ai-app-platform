import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.release_manager import ReleaseManager


class ReleaseManagerTests(unittest.TestCase):
    def _spec(self, targets):
        return AppSpec("Release Demo", "release-demo", "demo", "todo", [], targets)

    def _ready(self, root: Path, ready=True):
        path = root / ".aiapp/reports/build_readiness.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"preview_ready": ready}), encoding="utf-8")

    def test_web_requires_real_zip_and_matching_checksum_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._ready(root)
            folder = root / "artifacts/web"
            folder.mkdir(parents=True)
            artifact = folder / "release-demo-web.zip"
            artifact.write_bytes(b"zip")
            digest = hashlib.sha256(b"zip").hexdigest()
            (folder / "release-demo-web.manifest.json").write_text(
                json.dumps({"artifact": artifact.name, "sha256": digest}),
                encoding="utf-8",
            )
            report = ReleaseManager().assess(root, self._spec(["web"]))
            state = report.targets[0]
            self.assertEqual(state.artifact_status, "portable_bundle")
            self.assertEqual(state.distribution_status, "approval_required")
            self.assertTrue(report.all_requested_artifacts_ready)

    def test_debug_apk_is_real_artifact_but_not_store_ready(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._ready(root)
            folder = root / "artifacts/android"
            folder.mkdir(parents=True)
            (folder / "release-demo-debug.apk").write_bytes(b"apk")
            report = ReleaseManager().assess(root, self._spec(["android"]))
            state = report.targets[0]
            self.assertEqual(state.artifact_status, "debug_apk")
            self.assertEqual(state.distribution_status, "debug_only")
            self.assertTrue(any("AAB" in x for x in state.blockers))

    def test_ios_source_is_not_mislabeled_as_downloadable_ipa(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._ready(root)
            (root / "mobile").mkdir()
            report = ReleaseManager().assess(root, self._spec(["ios"]))
            state = report.targets[0]
            self.assertEqual(state.artifact_status, "source_only")
            self.assertEqual(state.artifacts, ())
            self.assertFalse(report.all_requested_artifacts_ready)

    def test_failed_quality_gate_blocks_existing_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._ready(root, False)
            folder = root / "artifacts/windows"
            folder.mkdir(parents=True)
            (folder / "release-demo.exe").write_bytes(b"exe")
            report = ReleaseManager().assess(root, self._spec(["windows"]))
            state = report.targets[0]
            self.assertEqual(state.artifact_status, "not_ready")
            self.assertEqual(state.artifacts, ())

    def test_release_manager_never_claims_auto_publish(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._ready(root)
            report = ReleaseManager().assess(root, self._spec(["ios", "android"]))
            self.assertTrue(report.external_release_requires_approval)
            for state in report.targets:
                self.assertNotEqual(state.distribution_status, "published")


if __name__ == "__main__":
    unittest.main()
