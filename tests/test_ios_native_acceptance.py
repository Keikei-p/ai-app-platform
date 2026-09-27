import plistlib
import tempfile
import unittest
from pathlib import Path

from src.tools.ios_native_acceptance import discover_app, discover_workspace, verify_simulator_app


class IOSNativeAcceptanceHelpersTests(unittest.TestCase):
    def test_workspace_discovery_requires_exactly_one_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(RuntimeError):
                discover_workspace(root)
            (root / "Demo.xcworkspace").mkdir()
            self.assertEqual(discover_workspace(root).name, "Demo.xcworkspace")
            (root / "Other.xcworkspace").mkdir()
            with self.assertRaises(RuntimeError):
                discover_workspace(root)

    def test_app_discovery_requires_debug_simulator_product(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            product = root / "Build" / "Products" / "Debug-iphonesimulator" / "Demo.app"
            product.mkdir(parents=True)
            self.assertEqual(discover_app(root), product)

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
            bundle_id, size = verify_simulator_app(app)
            self.assertEqual(bundle_id, "com.example.demo")
            self.assertGreater(size, 0)


if __name__ == "__main__":
    unittest.main()
