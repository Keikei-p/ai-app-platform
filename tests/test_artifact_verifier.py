import hashlib
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.core.artifact_verifier import ArtifactVerifier


class ArtifactVerifierTests(unittest.TestCase):
    def _zip(self, path: Path, files: dict[str, bytes | str]):
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)

    def _manifest(self, artifact: Path, path: Path, **extra):
        payload = {
            "artifact": artifact.name,
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            **extra,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_web_zip_requires_index_and_matching_checksum(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "app.zip"
            manifest = root / "app.manifest.json"
            self._zip(artifact, {"index.html": "ok", "app.js": "ok"})
            self._manifest(artifact, manifest)
            result = ArtifactVerifier().verify_web_zip(artifact, manifest)
            self.assertTrue(result.valid)
            manifest.write_text(json.dumps({"artifact": artifact.name, "sha256": "0" * 64}), encoding="utf-8")
            self.assertFalse(ArtifactVerifier().verify_web_zip(artifact, manifest).valid)

    def test_windows_exe_requires_mz_and_pe_signatures(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            exe = root / "demo.exe"
            data = bytearray(256)
            data[:2] = b"MZ"
            struct.pack_into("<I", data, 0x3C, 0x80)
            data[0x80:0x84] = b"PE\x00\x00"
            exe.write_bytes(data)
            self.assertTrue(ArtifactVerifier().verify_windows_exe(exe).valid)
            exe.write_bytes(b"MZbad")
            self.assertFalse(ArtifactVerifier().verify_windows_exe(exe).valid)

    def test_apk_requires_manifest_and_dex(self):
        with tempfile.TemporaryDirectory() as td:
            apk = Path(td) / "demo.apk"
            self._zip(apk, {"AndroidManifest.xml": b"x", "classes.dex": b"y"})
            self.assertTrue(ArtifactVerifier().verify_android_apk(apk).valid)
            self._zip(apk, {"AndroidManifest.xml": b"x"})
            self.assertFalse(ArtifactVerifier().verify_android_apk(apk).valid)

    def test_ios_source_requires_expected_files_and_source_only_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "demo-ios-source.zip"
            manifest = root / "demo-ios-source.manifest.json"
            self._zip(artifact, {
                "mobile/package.json": "{}",
                "mobile/app.json": "{}",
                "mobile/App.tsx": "export default null",
            })
            self._manifest(artifact, manifest, signed_ipa=False)
            self.assertTrue(ArtifactVerifier().verify_ios_source_zip(artifact, manifest).valid)
            self._manifest(artifact, manifest, signed_ipa=True)
            self.assertFalse(ArtifactVerifier().verify_ios_source_zip(artifact, manifest).valid)

    def test_archive_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "bad.zip"
            manifest = root / "bad.manifest.json"
            self._zip(artifact, {"index.html": "ok", "../escape.txt": "bad"})
            self._manifest(artifact, manifest)
            result = ArtifactVerifier().verify_web_zip(artifact, manifest)
            self.assertFalse(result.valid)
            self.assertTrue(any("unsafe" in x.lower() for x in result.failures))


if __name__ == "__main__":
    unittest.main()
