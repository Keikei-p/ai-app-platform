from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any
import json
import struct
import zipfile


@dataclass(frozen=True)
class ArtifactVerification:
    kind: str
    valid: bool
    sha256: str
    checks: tuple[str, ...]
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checks"] = list(self.checks)
        data["failures"] = list(self.failures)
        return data


class ArtifactVerifier:
    """Verify artifact structure before ReleaseManager calls it usable.

    File extensions and non-zero size alone are not evidence. This verifier
    inspects format signatures, archive contents and checksum manifests without
    executing the artifact.
    """

    def verify_web_zip(self, artifact: Path, manifest: Path | None) -> ArtifactVerification:
        checks: list[str] = []
        failures: list[str] = []
        digest = self._safe_sha(artifact, failures)
        names = self._zip_names(artifact, failures)
        if names is not None:
            checks.append("valid_zip")
            if "index.html" in names:
                checks.append("index_html")
            else:
                failures.append("index.html missing from Web bundle")
            if self._safe_archive_names(names):
                checks.append("safe_paths")
            else:
                failures.append("archive contains unsafe path")
        self._manifest_checksum(artifact, manifest, digest, checks, failures)
        return ArtifactVerification("web_zip", not failures, digest, tuple(checks), tuple(failures))

    def verify_windows_exe(self, artifact: Path, manifest: Path | None) -> ArtifactVerification:
        checks: list[str] = []
        failures: list[str] = []
        digest = self._safe_sha(artifact, failures)
        if not failures:
            try:
                data = artifact.read_bytes()
                if len(data) < 132 or data[:2] != b"MZ":
                    failures.append("Windows artifact is not a PE executable")
                else:
                    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
                    if pe_offset + 4 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\x00\x00":
                        failures.append("Windows PE signature is missing")
                    else:
                        checks.extend(("mz_header", "pe_signature"))
            except OSError as exc:
                failures.append(f"Windows artifact unreadable: {exc}")
        manifest_data = self._manifest_checksum(artifact, manifest, digest, checks, failures)
        if manifest_data is not None:
            if manifest_data.get("self_test_passed") is True:
                checks.append("self_test_passed")
            else:
                failures.append("Windows manifest does not prove self-test success")
            if manifest_data.get("signed") is False:
                checks.append("unsigned_declared")
        return ArtifactVerification("windows_exe", not failures, digest, tuple(checks), tuple(failures))

    def verify_android_apk(self, artifact: Path, manifest: Path | None) -> ArtifactVerification:
        checks: list[str] = []
        failures: list[str] = []
        digest = self._safe_sha(artifact, failures)
        names = self._zip_names(artifact, failures)
        if names is not None:
            checks.append("valid_zip")
            required = ("AndroidManifest.xml", "classes.dex")
            for name in required:
                if name in names:
                    checks.append(name)
                else:
                    failures.append(f"{name} missing from APK")
            if self._safe_archive_names(names):
                checks.append("safe_paths")
            else:
                failures.append("APK contains unsafe path")
        manifest_data = self._manifest_checksum(artifact, manifest, digest, checks, failures)
        if manifest_data is not None:
            if manifest_data.get("build_variant") == "debug":
                checks.append("debug_variant")
            else:
                failures.append("APK manifest does not identify a debug build")
            if manifest_data.get("store_ready") is False:
                checks.append("not_store_ready")
            else:
                failures.append("debug APK must not be marked store-ready")
            if manifest_data.get("production_signing_verified") is False:
                checks.append("production_signing_not_claimed")
            else:
                failures.append("debug APK must not claim production signing")
        return ArtifactVerification("android_apk", not failures, digest, tuple(checks), tuple(failures))

    def verify_android_aab(self, artifact: Path, manifest: Path | None) -> ArtifactVerification:
        checks: list[str] = []
        failures: list[str] = []
        digest = self._safe_sha(artifact, failures)
        names = self._zip_names(artifact, failures)
        if names is not None:
            checks.append("valid_zip")
            if "base/manifest/AndroidManifest.xml" in names:
                checks.append("base_manifest")
            else:
                failures.append("base AndroidManifest.xml missing from AAB")
            if "base/dex/classes.dex" in names:
                checks.append("base_dex")
            else:
                failures.append("base classes.dex missing from AAB")
            if self._safe_archive_names(names):
                checks.append("safe_paths")
            else:
                failures.append("AAB contains unsafe path")
        manifest_data = self._manifest_checksum(artifact, manifest, digest, checks, failures)
        if manifest_data is not None:
            if manifest_data.get("production_signing_verified") is True:
                checks.append("production_signing_verified")
            else:
                failures.append("AAB production signing has not been verified")
            if manifest_data.get("store_ready") is True:
                checks.append("store_ready")
            else:
                failures.append("AAB is not marked store-ready")
        return ArtifactVerification("android_aab", not failures, digest, tuple(checks), tuple(failures))

    def verify_ios_source_zip(self, artifact: Path, manifest: Path | None) -> ArtifactVerification:
        checks: list[str] = []
        failures: list[str] = []
        digest = self._safe_sha(artifact, failures)
        names = self._zip_names(artifact, failures)
        if names is not None:
            checks.append("valid_zip")
            for name in ("mobile/package.json", "mobile/app.json", "mobile/App.tsx"):
                if name in names:
                    checks.append(name)
                else:
                    failures.append(f"{name} missing from iOS source bundle")
            if self._safe_archive_names(names):
                checks.append("safe_paths")
            else:
                failures.append("iOS source ZIP contains unsafe path")
        manifest_data = self._manifest_checksum(artifact, manifest, digest, checks, failures)
        if manifest_data is not None:
            if manifest_data.get("signed_ipa") is False:
                checks.append("source_only_manifest")
            else:
                failures.append("iOS source manifest must explicitly state signed_ipa=false")
        return ArtifactVerification("ios_source_zip", not failures, digest, tuple(checks), tuple(failures))

    def verify_ipa(self, artifact: Path, manifest: Path | None) -> ArtifactVerification:
        checks: list[str] = []
        failures: list[str] = []
        digest = self._safe_sha(artifact, failures)
        names = self._zip_names(artifact, failures)
        if names is not None:
            checks.append("valid_zip")
            has_app = any(
                name.startswith("Payload/") and ".app/" in name and name.endswith("Info.plist")
                for name in names
            )
            if has_app:
                checks.append("payload_app_info_plist")
            else:
                failures.append("IPA Payload app Info.plist is missing")
            if self._safe_archive_names(names):
                checks.append("safe_paths")
            else:
                failures.append("IPA contains unsafe path")
        manifest_data = self._manifest_checksum(artifact, manifest, digest, checks, failures)
        if manifest_data is not None:
            if manifest_data.get("apple_signing_verified") is True:
                checks.append("apple_signing_verified")
            else:
                failures.append("Apple signing has not been verified")
            if manifest_data.get("store_ready") is True:
                checks.append("store_ready")
            else:
                failures.append("IPA is not marked store-ready")
        return ArtifactVerification("ios_ipa", not failures, digest, tuple(checks), tuple(failures))

    @staticmethod
    def _safe_sha(path: Path, failures: list[str]) -> str:
        try:
            if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
                failures.append("artifact is missing, empty or unsafe")
                return ""
            return sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            failures.append(f"artifact unreadable: {exc}")
            return ""

    @staticmethod
    def _zip_names(path: Path, failures: list[str]) -> set[str] | None:
        try:
            if not zipfile.is_zipfile(path):
                failures.append("artifact is not a valid ZIP container")
                return None
            with zipfile.ZipFile(path, "r") as archive:
                bad = archive.testzip()
                if bad is not None:
                    failures.append(f"archive CRC failure: {bad}")
                    return None
                return set(archive.namelist())
        except (OSError, zipfile.BadZipFile) as exc:
            failures.append(f"archive unreadable: {exc}")
            return None

    @staticmethod
    def _safe_archive_names(names: set[str]) -> bool:
        for raw in names:
            normalized = raw.replace("\\", "/")
            path = PurePosixPath(normalized)
            if path.is_absolute() or ".." in path.parts:
                return False
        return True

    @staticmethod
    def _manifest_checksum(
        artifact: Path,
        manifest: Path | None,
        digest: str,
        checks: list[str],
        failures: list[str],
    ) -> dict[str, Any] | None:
        if manifest is None or not manifest.is_file() or manifest.is_symlink():
            failures.append("checksum manifest is missing")
            return None
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"checksum manifest is invalid: {exc}")
            return None
        if not isinstance(data, dict):
            failures.append("checksum manifest root must be an object")
            return None
        if str(data.get("artifact") or "") != artifact.name:
            failures.append("checksum manifest artifact name does not match")
        elif str(data.get("sha256") or "") != digest:
            failures.append("checksum manifest SHA-256 does not match")
        else:
            checks.append("checksum_manifest")
        return data
