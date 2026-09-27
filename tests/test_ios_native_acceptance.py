import plistlib
import tempfile
import unittest
from pathlib import Path

from src.core.ios_simulator_packager import IOSSimulatorPackager


class IOSNativeAcceptanceHelpersTests(unittest.TestCase):
    def test_workspace_discovery_requires_exactly_one_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(RuntimeError):
                IOSSimulatorPackager.discover_workspace(root)
            (root / "Demo.xcworkspace").mkdir()
            self.assertEqual(
                IOSSimulatorPackager.discover_workspace(root).name,
                "Demo.xcworkspace",
            )
            (root / "Other.xcworkspace").mkdir()
            with self.assertRaises(RuntimeError):
                IOSSimulatorPackager.discover_workspace(root)

    def test_app_discovery_requires_debug_simulator_product(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            product = (
                root
                / "Build"
                / "Products"
                / "Debug-iphonesimulator"
                / "Demo.app"
            )
            product.mkdir(parents=True)
            self.assertEqual(IOSSimulatorPackager.discover_app(root), product)

    def test_simulator_app_requires_valid_info_and_executable(self):
        with tempfile.TemporaryDirectory() as td:
            app = Path(td) / "Demo.app"
            app.mkdir()
            (app / "Info.plist").write_bytes(
                plistlib.dumps({
                    "CFBundleExecutable": "Demo",
                    "CFBundleIdentifier": "com.example.demo",
                })
            )
            (app / "Demo").write_bytes(b"mach-o-placeholder")
            bundle_id, executable, size = IOSSimulatorPackager.verify_app(app)
            self.assertEqual(bundle_id, "com.example.demo")
            self.assertEqual(executable, "Demo")
            self.assertGreater(size, 0)


if __name__ == "__main__":
    unittest.main()
