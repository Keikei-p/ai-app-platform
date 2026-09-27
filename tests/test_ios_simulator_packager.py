import json
import plistlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.core.artifact_verifier import ArtifactVerifier
from src.core.ios_simulator_packager import IOSSimulatorPackager


class IOSSimulatorPackagerTests(unittest.TestCase):
    def test_discovery_and_app_validation_helpers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ios = root / "ios"
            workspace = ios / "Demo.xcworkspace"
            workspace.mkdir(parents=True)
            self.assertEqual(
                IOSSimulatorPackager.discover_workspace(ios),
                workspace,
            )

            app = (
                root
                / "derived"
                / "Build"
                / "Products"
                / "Debug-iphonesimulator"
                / "Demo.app"
            )
            app.mkdir(parents=True)
            (app / "Info.plist").write_bytes(
                plistlib.dumps({
                    "CFBundleExecutable": "Demo",
                    "CFBundleIdentifier": "com.example.demo",
                })
            )
            (app / "Demo").write_bytes(b"binary")
            self.assertEqual(
                IOSSimulatorPackager.discover_app(root / "derived"),
                app,
            )
            bundle, executable, size = IOSSimulatorPackager.verify_app(app)
            self.assertEqual(bundle, "com.example.demo")
            self.assertEqual(executable, "Demo")
            self.assertGreater(size, 0)

    def test_simulator_zip_verifier_rejects_store_ready_claim(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "demo-simulator.app.zip"
            info = plistlib.dumps({
                "CFBundleExecutable": "Demo",
                "CFBundleIdentifier": "com.example.demo",
            })
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("Demo.app/Info.plist", info)
                archive.writestr("Demo.app/Demo", b"binary")
            import hashlib
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            manifest = root / "demo-simulator.app.manifest.json"
            manifest.write_text(
                json.dumps({
                    "artifact": artifact.name,
                    "sha256": digest,
                    "simulator_only": True,
                    "signed_ipa": False,
                    "apple_signing_verified": False,
                    "store_ready": True,
                    "bundle_identifier": "com.example.demo",
                    "executable": "Demo",
                }),
                encoding="utf-8",
            )
            result = ArtifactVerifier().verify_ios_simulator_zip(artifact, manifest)
            self.assertFalse(result.valid)
            self.assertTrue(any("store-ready" in x for x in result.failures))


if __name__ == "__main__":
    unittest.main()
