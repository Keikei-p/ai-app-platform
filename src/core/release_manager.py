from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import json

from .app_spec import AppSpec
from .artifact_verifier import ArtifactVerifier


@dataclass(frozen=True)
class TargetReleaseState:
    target: str
    requested: bool
    quality_verified: bool
    artifact_status: str
    artifacts: tuple[str, ...]
    checksums: tuple[str, ...]
    distribution_status: str
    blockers: tuple[str, ...]
    next_step: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["artifacts"] = list(self.artifacts)
        data["checksums"] = list(self.checksums)
        data["blockers"] = list(self.blockers)
        return data


@dataclass(frozen=True)
class ReleaseReport:
    quality_verified: bool
    requested_targets: tuple[str, ...]
    targets: tuple[TargetReleaseState, ...]
    all_requested_artifacts_ready: bool
    external_release_requires_approval: bool
    created_from_evidence: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "quality_verified": self.quality_verified,
            "requested_targets": list(self.requested_targets),
            "targets": [x.to_dict() for x in self.targets],
            "all_requested_artifacts_ready": self.all_requested_artifacts_ready,
            "external_release_requires_approval": self.external_release_requires_approval,
            "created_from_evidence": self.created_from_evidence,
        }


class ReleaseManager:
    """Evidence-only release readiness across Web/Windows/Android/iOS.

    It never publishes, signs, uploads, buys, submits, or invents artifacts.
    """

    ORDER = ("web", "windows", "android", "ios")

    def __init__(self, verifier: ArtifactVerifier | None = None):
        self.verifier = verifier or ArtifactVerifier()

    def assess(self, project_dir: Path, spec: AppSpec) -> ReleaseReport:
        project_dir = Path(project_dir)
        readiness = self._json(project_dir / ".aiapp" / "reports" / "build_readiness.json")
        quality = bool(readiness.get("preview_ready"))
        requested = tuple(x for x in self.ORDER if x in {str(t).lower() for t in spec.targets})
        states = tuple(self._target(project_dir, target, quality) for target in requested)
        all_ready = bool(states) and all(
            x.artifact_status in {"portable_bundle", "local_executable", "debug_apk", "store_bundle", "signed_ipa"}
            for x in states
        )
        return ReleaseReport(
            quality_verified=quality,
            requested_targets=requested,
            targets=states,
            all_requested_artifacts_ready=all_ready,
            external_release_requires_approval=True,
            created_from_evidence=True,
        )

    def save(self, project_dir: Path, report: ReleaseReport) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "release_manager.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _target(self, root: Path, target: str, quality: bool) -> TargetReleaseState:
        if target == "web":
            candidates = self._files(root / "artifacts" / "web", {".zip"})
            manifest = next(iter(sorted((root / "artifacts" / "web").glob("*.manifest.json"))), None) if (root / "artifacts" / "web").is_dir() else None
            verified: tuple[Path, ...] = ()
            blockers: list[str] = []
            if not quality:
                blockers.append("quality gates have not verified preview readiness")
            if not candidates:
                blockers.append("Web ZIP does not exist")
            else:
                verification = self.verifier.verify_web_zip(candidates[0], manifest)
                if verification.valid:
                    verified = (candidates[0],)
                else:
                    blockers.extend(f"Web artifact invalid: {x}" for x in verification.failures)
            ready = quality and bool(verified)
            return self._state(
                target, quality,
                "portable_bundle" if ready else "not_ready",
                verified if ready else (),
                "approval_required" if ready else "blocked",
                blockers,
                "Human approval is required before production deployment." if ready else "Build and verify the Web ZIP.",
            )

        if target == "windows":
            candidates = self._files(root / "artifacts" / "windows", {".exe"})
            blockers: list[str] = []
            verified_rows: list[Path] = []
            for artifact in candidates:
                manifest = artifact.with_name(artifact.stem + ".manifest.json")
                if self.verifier.verify_windows_exe(artifact, manifest).valid:
                    verified_rows.append(artifact)
            verified = tuple(verified_rows)
            if not quality:
                blockers.append("quality gates have not verified preview readiness")
            if not candidates:
                blockers.append("Windows EXE does not exist")
            elif not verified:
                blockers.append("Windows EXE failed structure, checksum, or self-test evidence verification")
            ready = quality and bool(verified)
            return self._state(
                target, quality,
                "local_executable" if ready else "not_ready",
                verified if ready else (),
                "local_download_ready" if ready else "blocked",
                blockers,
                "Code signing/public distribution remains a separate human-controlled release step." if ready else "Build and self-test the Windows EXE.",
            )

        if target == "android":
            aab_candidates = self._files(root / "artifacts" / "android", {".aab"})
            apk_candidates = self._files(root / "artifacts" / "android", {".apk"})

            aab_verifications = [
                (
                    x,
                    self.verifier.verify_android_aab(
                        x,
                        x.with_name(x.stem + ".manifest.json"),
                    ),
                )
                for x in aab_candidates
            ]
            apk_verifications = [
                (
                    x,
                    self.verifier.verify_android_apk(
                        x,
                        x.with_name(x.stem + ".manifest.json"),
                    ),
                )
                for x in apk_candidates
            ]
            aabs = tuple(x for x, verification in aab_verifications if verification.valid)
            apks = tuple(x for x, verification in apk_verifications if verification.valid)

            blockers: list[str] = []
            if not quality:
                blockers.append("quality gates have not verified preview readiness")
            if aabs:
                status = "store_bundle" if quality else "not_ready"
                artifacts = aabs if quality else ()
                distribution = "approval_required" if quality else "blocked"
                next_step = "Verify production signing, Play Console requirements, then request explicit store-submission approval."
            elif apks:
                status = "debug_apk" if quality else "not_ready"
                artifacts = apks if quality else ()
                distribution = "debug_only" if quality else "blocked"
                blockers.append("production AAB/signing has not been verified")
                next_step = "Use the APK for testing; production AAB/signing remains a separate approval-gated step."
            else:
                status = "not_ready"
                artifacts = ()
                distribution = "blocked"
                invalid = [*aab_verifications, *apk_verifications]
                if invalid:
                    blockers.append("Android artifact failed structural, checksum, or release-evidence verification")
                    for artifact, verification in invalid:
                        for failure in verification.failures[:6]:
                            blockers.append(f"{artifact.name}: {failure}")
                else:
                    blockers.append("Android APK/AAB does not exist")
                next_step = "Prepare Android build dependencies and build a verified debug APK."
            return self._state(target, quality, status, artifacts, distribution, blockers, next_step)

        if target == "ios":
            folder = root / "artifacts" / "ios"
            ipa_candidates = self._files(folder, {".ipa"})
            ipas = tuple(
                x for x in ipa_candidates
                if self.verifier.verify_ipa(x, x.with_name(x.stem + ".manifest.json")).valid
            )
            simulator_candidates = tuple(
                x for x in self._files(folder, {".zip"})
                if "simulator.app" in x.name.lower()
            )
            simulator_zips: list[Path] = []
            for simulator in simulator_candidates:
                manifest = simulator.with_name(simulator.stem + ".manifest.json")
                if self.verifier.verify_ios_simulator_zip(simulator, manifest).valid:
                    simulator_zips.append(simulator)

            source_candidates = tuple(
                x for x in self._files(folder, {".zip"})
                if "source" in x.stem.lower()
            )
            source_zips: list[Path] = []
            for source in source_candidates:
                manifest = folder / (source.stem + ".manifest.json")
                if self.verifier.verify_ios_source_zip(source, manifest).valid:
                    source_zips.append(source)

            blockers: list[str] = []
            if not quality:
                blockers.append("quality gates have not verified preview readiness")
            if ipas and quality:
                return self._state(
                    target, quality, "signed_ipa", ipas, "approval_required",
                    blockers,
                    "Verify Apple signing/provisioning and request explicit distribution/App Store approval.",
                )

            if ipa_candidates and not ipas:
                blockers.append("iOS IPA failed structure, checksum, or signing-evidence verification")
            else:
                blockers.append("signed iOS IPA does not exist")

            if simulator_zips and quality:
                blockers.append("Simulator build is not installable on a physical iPhone/iPad")
                return self._state(
                    target,
                    quality,
                    "simulator_bundle",
                    tuple(simulator_zips),
                    "simulator_only",
                    blockers,
                    "Native iOS compilation is verified for Simulator. Apple signing and a device IPA remain separate approval-gated steps.",
                )

            if simulator_candidates and not simulator_zips:
                blockers.append("iOS Simulator bundle failed checksum or structure verification")

            if source_zips and quality:
                return self._state(
                    target, quality, "source_bundle", tuple(source_zips), "source_only",
                    blockers,
                    "iOS source is downloadable; use macOS/Xcode or an approved build service with Apple signing credentials to produce an IPA.",
                )
            if source_candidates and not source_zips:
                blockers.append("iOS source bundle failed checksum or structure verification")
            return self._state(
                target, quality, "source_only", (), "blocked", blockers,
                "Use macOS/Xcode or an approved build service with Apple signing credentials to produce an IPA.",
            )

        return self._state(target, quality, "unsupported", (), "blocked", ("unsupported target",), "No release adapter exists.")

    def _state(
        self,
        target: str,
        quality: bool,
        artifact_status: str,
        artifacts: tuple[Path, ...],
        distribution_status: str,
        blockers: list[str] | tuple[str, ...],
        next_step: str,
    ) -> TargetReleaseState:
        return TargetReleaseState(
            target=target,
            requested=True,
            quality_verified=quality,
            artifact_status=artifact_status,
            artifacts=tuple(str(x) for x in artifacts),
            checksums=tuple(self._sha256(x) for x in artifacts),
            distribution_status=distribution_status,
            blockers=tuple(dict.fromkeys(str(x) for x in blockers if str(x).strip())),
            next_step=next_step,
        )

    @staticmethod
    def _files(root: Path, suffixes: set[str]) -> tuple[Path, ...]:
        if not root.is_dir():
            return ()
        return tuple(
            x for x in sorted(root.iterdir())
            if x.is_file() and not x.is_symlink() and x.suffix.lower() in suffixes and x.stat().st_size > 0
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        return sha256(path.read_bytes()).hexdigest()

    def _web_manifest_valid(self, artifact: Path, manifest: Path | None) -> bool:
        if manifest is None or not manifest.is_file():
            return False
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            return (
                str(data.get("artifact") or "") == artifact.name
                and str(data.get("sha256") or "") == self._sha256(artifact)
            )
        except Exception:
            return False

    @staticmethod
    def _json(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
