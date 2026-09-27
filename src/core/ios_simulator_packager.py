from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
import json
import os
import plistlib
import shutil
import subprocess
import sys
import zipfile

from .app_spec import AppSpec
from .artifact_verifier import ArtifactVerifier
from .database import log_event


@dataclass(frozen=True)
class IOSSimulatorBuildResult:
    attempted: bool
    built: bool
    artifact: Path | None
    manifest: Path | None
    sha256: str
    bundle_identifier: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["artifact"] = str(self.artifact) if self.artifact else None
        data["manifest"] = str(self.manifest) if self.manifest else None
        return data


class IOSSimulatorPackager:
    """Compile a generated Expo project into an unsigned iOS Simulator app.

    This is build evidence only. It never creates a device IPA, Apple signing
    credentials, provisioning profiles, TestFlight uploads, or App Store submissions.
    """

    def __init__(
        self,
        *,
        which: Callable[[str], str | None] | None = None,
        runner: Callable[[list[str], Path, int], Any] | None = None,
        verifier: ArtifactVerifier | None = None,
    ):
        self.which = which or shutil.which
        self.runner = runner or self._run
        self.verifier = verifier or ArtifactVerifier()

    def build(
        self,
        project_dir: Path,
        spec: AppSpec,
        *,
        timeout: int = 1200,
    ) -> IOSSimulatorBuildResult:
        root = Path(project_dir)
        if "ios" not in spec.targets:
            return IOSSimulatorBuildResult(
                False, False, None, None, "", "", "ios target not requested"
            )
        if sys.platform != "darwin":
            return IOSSimulatorBuildResult(
                False,
                False,
                None,
                None,
                "",
                "",
                "iOS Simulator native builds require a macOS/Xcode host",
            )

        mobile = root / "mobile"
        if not (mobile / "package.json").is_file():
            return IOSSimulatorBuildResult(
                False, False, None, None, "", "", "mobile source is missing"
            )
        if not (mobile / "node_modules").is_dir():
            return IOSSimulatorBuildResult(
                False,
                False,
                None,
                None,
                "",
                "",
                "mobile dependencies are not installed; Aivy will not install them implicitly",
            )
        if not self.which("npx") or not self.which("xcodebuild"):
            return IOSSimulatorBuildResult(
                False, False, None, None, "", "", "npx/Xcode is not available"
            )

        derived = root / ".aiapp-build" / "ios-simulator"
        if derived.exists():
            shutil.rmtree(derived)
        derived.mkdir(parents=True, exist_ok=True)

        try:
            self.runner(
                ["npx", "expo", "prebuild", "--platform", "ios", "--clean"],
                mobile,
                min(timeout, 900),
            )
            ios_dir = mobile / "ios"
            workspace = self.discover_workspace(ios_dir)
            scheme = self.discover_scheme(workspace, mobile)
            self.runner(
                [
                    "xcodebuild",
                    "-workspace",
                    str(workspace),
                    "-scheme",
                    scheme,
                    "-configuration",
                    "Debug",
                    "-sdk",
                    "iphonesimulator",
                    "-destination",
                    "generic/platform=iOS Simulator",
                    "-derivedDataPath",
                    str(derived),
                    "CODE_SIGNING_ALLOWED=NO",
                    "build",
                ],
                mobile,
                timeout,
            )
            app = self.discover_app(derived)
            bundle_id, executable_name, executable_bytes = self.verify_app(app)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            detail = f"{type(exc).__name__}: {exc}"
            log_event(
                "packager.ios.simulator_failed",
                detail,
                spec.slug,
                "ios-simulator-packager",
            )
            return IOSSimulatorBuildResult(
                True, False, None, None, "", "", detail
            )

        artifact_dir = root / "artifacts" / "ios"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact = artifact_dir / f"{spec.slug}-simulator.app.zip"
        manifest = artifact_dir / f"{spec.slug}-simulator.app.manifest.json"
        if artifact.exists():
            artifact.unlink()

        with zipfile.ZipFile(artifact, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(app.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                rel = path.relative_to(app.parent)
                archive.write(path, rel.as_posix())

        digest = sha256(artifact.read_bytes()).hexdigest()
        manifest.write_text(
            json.dumps(
                {
                    "target": "ios-simulator",
                    "artifact": artifact.name,
                    "sha256": digest,
                    "bundle_identifier": bundle_id,
                    "executable": executable_name,
                    "executable_bytes": executable_bytes,
                    "simulator_only": True,
                    "signed_ipa": False,
                    "apple_signing_verified": False,
                    "store_ready": False,
                    "distribution": (
                        "iOS Simulator testing only; device IPA, Apple signing, "
                        "TestFlight and App Store submission require separate approval-gated steps"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        verification = self.verifier.verify_ios_simulator_zip(artifact, manifest)
        if not verification.valid:
            failures = "; ".join(verification.failures[:8])
            detail = "iOS Simulator artifact verification failed: " + (failures or "unknown")
            try:
                artifact.unlink(missing_ok=True)
                manifest.unlink(missing_ok=True)
            except OSError:
                pass
            log_event(
                "packager.ios.simulator_verification_failed",
                detail,
                spec.slug,
                "ios-simulator-packager",
            )
            return IOSSimulatorBuildResult(
                True, False, None, None, "", bundle_id, detail
            )

        detail = (
            "iOS Simulator app compiled with Xcode and artifact evidence verified. "
            "This is not a signed device IPA and is not App Store ready."
        )
        log_event(
            "packager.ios.simulator_built",
            f"{artifact.name} sha256={digest}",
            spec.slug,
            "ios-simulator-packager",
        )
        return IOSSimulatorBuildResult(
            True, True, artifact, manifest, digest, bundle_id, detail
        )

    def discover_scheme(self, workspace: Path, mobile: Path) -> str:
        result = self.runner(
            ["xcodebuild", "-workspace", str(workspace), "-list", "-json"],
            mobile,
            180,
        )
        stdout = str(getattr(result, "stdout", "") or "")
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("xcodebuild did not return scheme JSON") from exc
        workspace_data = data.get("workspace") if isinstance(data, dict) else None
        schemes = workspace_data.get("schemes") if isinstance(workspace_data, dict) else None
        clean = [str(x).strip() for x in schemes or [] if str(x).strip()]
        if not clean:
            raise RuntimeError("generated iOS workspace has no build scheme")

        ios_dir = workspace.parent
        projects = sorted(
            path for path in ios_dir.glob("*.xcodeproj")
            if path.is_dir()
            and not path.is_symlink()
            and path.name.lower() != "pods.xcodeproj"
        )
        preferred = [path.stem for path in projects]
        for name in preferred:
            if name in clean:
                return name

        normalized = {
            self._normalize_scheme(name): name
            for name in clean
        }
        for name in preferred:
            match = normalized.get(self._normalize_scheme(name))
            if match:
                return match

        if len(clean) == 1:
            return clean[0]
        raise RuntimeError(
            "could not identify the generated app scheme; "
            f"projects={preferred}, schemes={clean}"
        )

    @staticmethod
    def _normalize_scheme(value: str) -> str:
        return "".join(ch.lower() for ch in str(value) if ch.isalnum())

    @staticmethod
    def discover_workspace(ios_dir: Path) -> Path:
        rows = sorted(
            path for path in Path(ios_dir).glob("*.xcworkspace")
            if path.is_dir() and not path.is_symlink()
        )
        if len(rows) != 1:
            raise RuntimeError(
                f"expected exactly one generated iOS workspace, found {len(rows)}"
            )
        return rows[0]

    @classmethod
    def discover_app(cls, derived_data: Path) -> Path:
        root = Path(derived_data)
        rows: list[Path] = []
        for path in sorted(root.rglob("*.app")):
            if not path.is_dir() or path.is_symlink():
                continue
            if any(part in {"Index.noindex", "ModuleCache.noindex"} for part in path.parts):
                continue
            try:
                cls.verify_app(path)
            except RuntimeError:
                continue
            rows.append(path)
        if len(rows) != 1:
            relative = [
                path.relative_to(root).as_posix()
                for path in rows[:12]
            ]
            raise RuntimeError(
                "expected exactly one structurally valid iOS Simulator .app, "
                f"found {len(rows)}: {relative}"
            )
        return rows[0]

    @staticmethod
    def verify_app(app: Path) -> tuple[str, str, int]:
        info_path = Path(app) / "Info.plist"
        if not info_path.is_file() or info_path.is_symlink():
            raise RuntimeError("iOS Simulator app is missing Info.plist")
        try:
            info = plistlib.loads(info_path.read_bytes())
        except Exception as exc:
            raise RuntimeError("iOS Simulator Info.plist is invalid") from exc
        if not isinstance(info, dict):
            raise RuntimeError("iOS Simulator Info.plist root is invalid")
        executable_name = str(info.get("CFBundleExecutable") or "").strip()
        bundle_id = str(info.get("CFBundleIdentifier") or "").strip()
        if not executable_name or not bundle_id:
            raise RuntimeError("iOS Simulator app metadata is incomplete")
        executable = Path(app) / executable_name
        if (
            not executable.is_file()
            or executable.is_symlink()
            or executable.stat().st_size <= 0
        ):
            raise RuntimeError("iOS Simulator app executable is missing or empty")
        return bundle_id, executable_name, executable.stat().st_size

    @staticmethod
    def _run(command: list[str], cwd: Path, timeout: int):
        env = dict(os.environ)
        env["CI"] = "1"
        env["EXPO_NO_GIT_STATUS"] = "1"
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
        if completed.returncode != 0:
            output = ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-14000:]
            raise RuntimeError(output or f"command failed with exit code {completed.returncode}")
        return completed
