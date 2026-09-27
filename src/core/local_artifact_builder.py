from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json

from .android_packager import AndroidPackager
from .app_spec import AppSpec
from .ios_source_packager import IOSSourcePackager
from .release_manager import ReleaseManager
from .web_packager import WebPackager
from .windows_packager import WindowsPackager


@dataclass(frozen=True)
class LocalArtifactBuildReport:
    status: str
    project_slug: str
    targets: tuple[str, ...]
    results: dict[str, dict[str, Any]]
    release: dict[str, Any]
    external_release_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["targets"] = list(self.targets)
        return data


class LocalArtifactBuilder:
    """Build only local artifacts after independent quality evidence passes.

    No dependency installation, production signing, public deployment, store
    submission, or credential handling is performed here.
    """

    SUPPORTED = ("web", "windows", "android", "ios")

    def __init__(
        self,
        *,
        web: WebPackager | None = None,
        windows: WindowsPackager | None = None,
        android: AndroidPackager | None = None,
        ios: IOSSourcePackager | None = None,
        release: ReleaseManager | None = None,
    ):
        self.web = web or WebPackager()
        self.windows = windows or WindowsPackager()
        self.android = android or AndroidPackager()
        self.ios = ios or IOSSourcePackager()
        self.release = release or ReleaseManager()

    def build(self, project_dir: Path, target: str | None = None) -> LocalArtifactBuildReport:
        root = Path(project_dir)
        spec = self._spec(root)
        self._assert_quality(root)

        requested = tuple(
            x for x in self.SUPPORTED
            if x in {str(t).lower() for t in spec.targets}
        )
        if target:
            clean = target.strip().lower()
            if clean not in self.SUPPORTED:
                raise ValueError("unsupported local build target")
            if clean not in requested:
                raise ValueError("target was not requested by app spec")
            targets = (clean,)
        else:
            targets = requested

        if not targets:
            raise ValueError("no supported build target is requested")

        results: dict[str, dict[str, Any]] = {}
        for name in targets:
            if name == "web":
                row = self.web.build(root, spec)
                results[name] = {
                    "built": bool(row.built),
                    "artifact": str(row.artifact) if row.artifact else None,
                    "manifest": str(row.manifest) if row.manifest else None,
                    "sha256": row.sha256,
                    "detail": row.detail,
                }
            elif name == "windows":
                row = self.windows.build(root, spec)
                results[name] = {
                    "attempted": bool(row.attempted),
                    "built": bool(row.built),
                    "artifact": str(row.artifact) if row.artifact else None,
                    "manifest": str(row.manifest) if row.manifest else None,
                    "sha256": row.sha256,
                    "self_test_passed": bool(row.self_test_passed),
                    "detail": row.detail,
                }
            elif name == "android":
                row = self.android.build_debug_apk(root, spec)
                results[name] = row.to_dict()
            elif name == "ios":
                row = self.ios.build(root, spec)
                results[name] = row.to_dict()

        release_report = self.release.assess(root, spec)
        self.release.save(root, release_report)

        built_any = any(bool(x.get("built")) for x in results.values())
        all_built = all(bool(x.get("built")) for x in results.values())
        status = "built" if all_built else ("partial" if built_any else "not_built")
        return LocalArtifactBuildReport(
            status=status,
            project_slug=spec.slug,
            targets=targets,
            results=results,
            release=release_report.to_dict(),
            external_release_performed=False,
        )

    @staticmethod
    def _spec(root: Path) -> AppSpec:
        path = root / "app_spec.json"
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError("app_spec.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("app_spec.json must be an object")
        return AppSpec(
            project_name=str(data.get("project_name") or ""),
            slug=str(data.get("slug") or ""),
            summary=str(data.get("summary") or ""),
            app_type=str(data.get("app_type") or "web_app"),
            features=[str(x) for x in data.get("features") or []],
            targets=[str(x).lower() for x in data.get("targets") or []],
            language=str(data.get("language") or "ja"),
            region=str(data.get("region") or "JP"),
            risk_level=str(data.get("risk_level") or "normal"),
            design_style=str(data.get("design_style") or "modern"),
            usage_context=str(data.get("usage_context") or ""),
        )

    @staticmethod
    def _assert_quality(root: Path) -> None:
        checks = (
            (root / ".aiapp" / "reports" / "build_readiness.json", "preview_ready"),
            (root / ".aiapp" / "reports" / "test_report.json", "passed"),
            (root / ".aiapp" / "reports" / "security_report.json", "passed"),
            (root / "design_review.json", "passed"),
        )
        failed: list[str] = []
        for path, key in checks:
            if not path.is_file() or path.is_symlink():
                failed.append(path.name + ":missing")
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                failed.append(path.name + ":invalid")
                continue
            if not isinstance(data, dict) or data.get(key) is not True:
                failed.append(path.name + ":not-passing")
        if failed:
            raise PermissionError(
                "local artifact build blocked by quality evidence: " + ", ".join(failed)
            )
