from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
import json
import os
import shutil
import subprocess

from .app_spec import AppSpec
from .database import log_event
from .artifact_verifier import ArtifactVerifier


@dataclass(frozen=True)
class AndroidBuildResult:
    attempted: bool
    built: bool
    artifact: Path | None
    sha256: str
    detail: str
    manifest: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["artifact"] = str(self.artifact) if self.artifact else None
        data["manifest"] = str(self.manifest) if self.manifest else None
        return data


class AndroidPackager:
    """Build a local unsigned/debug APK from an already-prepared Expo project.

    It never installs dependencies, signs production artifacts, creates AAB store
    releases, or submits to Google Play. Commands are fixed argv with shell=False.
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

    def build_debug_apk(
        self,
        project_dir: Path,
        spec: AppSpec,
        *,
        timeout: int = 900,
    ) -> AndroidBuildResult:
        project_dir = Path(project_dir)
        if "android" not in spec.targets:
            return AndroidBuildResult(False, False, None, "", "android target not requested")

        mobile = project_dir / "mobile"
        if not (mobile / "package.json").is_file():
            return AndroidBuildResult(False, False, None, "", "mobile source is missing")
        if not (mobile / "node_modules").is_dir():
            return AndroidBuildResult(
                False,
                False,
                None,
                "",
                "mobile dependencies are not installed; Aivy will not install them implicitly",
            )

        npx = "npx.cmd" if os.name == "nt" else "npx"
        if not self.which(npx):
            return AndroidBuildResult(False, False, None, "", "npx is not available")
        if not self.which("java"):
            return AndroidBuildResult(False, False, None, "", "Java is not available")
        sdk = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
        if not sdk or not Path(sdk).exists():
            return AndroidBuildResult(False, False, None, "", "Android SDK is not configured")

        try:
            self.runner(
                [npx, "expo", "prebuild", "--platform", "android", "--clean"],
                mobile,
                min(timeout, 600),
            )
            android = mobile / "android"
            gradle = android / ("gradlew.bat" if os.name == "nt" else "gradlew")
            if not gradle.is_file():
                raise RuntimeError("Expo prebuild did not create Gradle wrapper")
            if os.name != "nt":
                gradle.chmod(gradle.stat().st_mode | 0o111)
            self.runner(
                [str(gradle), "assembleDebug", "--no-daemon"],
                android,
                timeout,
            )
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            detail = f"{type(exc).__name__}: {exc}"
            log_event("packager.android.debug_failed", detail, spec.slug, "android-packager")
            return AndroidBuildResult(True, False, None, "", detail)

        source = mobile / "android" / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        if not source.is_file() or source.stat().st_size <= 0:
            detail = "Gradle completed but app-debug.apk was not produced"
            log_event("packager.android.debug_failed", detail, spec.slug, "android-packager")
            return AndroidBuildResult(True, False, None, "", detail)

        artifact_dir = project_dir / "artifacts" / "android"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact = artifact_dir / f"{spec.slug}-debug.apk"
        shutil.copy2(source, artifact)
        digest = sha256(artifact.read_bytes()).hexdigest()
        manifest = artifact_dir / f"{spec.slug}-debug.manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "target": "android",
                    "artifact": artifact.name,
                    "sha256": digest,
                    "build_variant": "debug",
                    "production_signing_verified": False,
                    "store_ready": False,
                    "distribution": "testing only; production AAB/signing/store submission require explicit human approval",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        verification = self.verifier.verify_android_apk(artifact, manifest)
        if not verification.valid:
            failures = "; ".join(verification.failures[:8]) or "unknown APK verification failure"
            detail = "Android debug APK verification failed: " + failures
            log_event(
                "packager.android.debug_verification_failed",
                detail,
                spec.slug,
                "android-packager",
            )
            try:
                artifact.unlink(missing_ok=True)
                manifest.unlink(missing_ok=True)
            except OSError:
                pass
            return AndroidBuildResult(True, False, None, "", detail, None)

        log_event(
            "packager.android.debug_built",
            f"{artifact.name} sha256={digest}",
            spec.slug,
            "android-packager",
        )
        return AndroidBuildResult(
            True,
            True,
            artifact,
            digest,
            "Android debug APK built and structurally verified. Production AAB/signing/store submission remain approval-gated.",
            manifest,
        )

    @staticmethod
    def _run(command: list[str], cwd: Path, timeout: int) -> None:
        env = dict(os.environ)
        env["CI"] = "1"
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
            output = ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-8000:]
            raise RuntimeError(output or f"command failed with exit code {completed.returncode}")
