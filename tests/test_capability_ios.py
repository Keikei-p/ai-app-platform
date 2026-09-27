import hashlib
import json
import plistlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.capability import CapabilityAssessor


class IOSCapabilityEvidenceTests(unittest.TestCase):
    def _spec(self):
        return AppSpec(
            project_name="Demo",
            slug="demo",
            summary="demo",
            app_type="todo",
            features=[],
            targets=["ios"],
        )

    def _zip(self, path: Path, files: dict[str, bytes | str]):
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)

    def _manifest(self, artifact: Path, extra: dict):
        payload = {
            "artifact": artifact.name,
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            **extra,
        }
        artifact.with_name(artifact.stem + ".manifest.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def test_source_bundle_does_not_clear_signed_ipa_gap(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "artifacts/ios/demo-ios-source.zip"
            self._zip(
                artifact,
                {
                    "mobile/package.json": "{}",
                    "mobile/app.json": "{}",
                    "mobile/App.tsx": "export default function App(){}",
                },
            )
            self._manifest(artifact, {"signed_ipa": False})
            gaps = CapabilityAssessor().assess(self._spec(), root)
            gap = next(x for x in gaps if x.key == "ios_binary")
            self.assertIn("iOSソース", gap.reason)

    def test_simulator_bundle_records_progress_but_keeps_device_gap(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "artifacts/ios/demo-simulator.app.zip"
            info = plistlib.dumps({
                "CFBundleExecutable": "Demo",
                "CFBundleIdentifier": "com.example.demo",
            })
            self._zip(
                artifact,
                {
                    "Demo.app/Info.plist": info,
                    "Demo.app/Demo": b"binary",
                },
            )
            self._manifest(
                artifact,
                {
                    "bundle_identifier": "com.example.demo",
                    "executable": "Demo",
                    "simulator_only": True,
                    "signed_ipa": False,
                    "apple_signing_verified": False,
                    "store_ready": False,
                },
            )
            gaps = CapabilityAssessor().assess(self._spec(), root)
            gap = next(x for x in gaps if x.key == "ios_binary")
            self.assertIn("Simulator", gap.reason)
            self.assertIn(artifact.name, gap.evidence)

    def test_verified_signed_ipa_clears_ios_binary_gap(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "artifacts/ios/demo.ipa"
            self._zip(
                artifact,
                {
                    "Payload/Demo.app/Info.plist": plistlib.dumps({
                        "CFBundleIdentifier": "com.example.demo"
                    }),
                },
            )
            self._manifest(
                artifact,
                {
                    "apple_signing_verified": True,
                    "store_ready": True,
                },
            )
            gaps = CapabilityAssessor().assess(self._spec(), root)
            self.assertNotIn("ios_binary", {x.key for x in gaps})


if __name__ == "__main__":
    unittest.main()
