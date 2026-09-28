from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json

from .app_spec import AppSpec
from .dependency_guardian import DependencyGuardian
from .performance_guardian import PerformanceGuardian
from .accessibility_guardian import AccessibilityGuardian
from .requirement_guardian import RequirementGuardian
from .release_manager import ReleaseManager
from .secrets_guard import SecretsGuard


@dataclass(frozen=True)
class ReleaseGuardianReport:
    status: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    release: dict[str, Any]
    dependency: dict[str, Any]
    performance: dict[str, Any]
    accessibility: dict[str, Any]
    secrets: dict[str, Any]
    requirement: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blockers"] = list(self.blockers)
        data["warnings"] = list(self.warnings)
        return data


class ReleaseGuardian:
    """Final local release gate. It never publishes externally."""

    def __init__(self):
        self.release = ReleaseManager()
        self.dependencies = DependencyGuardian()
        self.performance = PerformanceGuardian()
        self.accessibility = AccessibilityGuardian()
        self.secrets = SecretsGuard()
        self.requirements = RequirementGuardian()

    def assess(
        self,
        project_dir: Path,
        spec: AppSpec,
        *,
        instruction: str = "",
        pipeline_report: dict[str, Any] | None = None,
        trace: dict[str, Any] | None = None,
    ) -> ReleaseGuardianReport:
        root = Path(project_dir)
        release = self.release.assess(root, spec)
        dependency = self.dependencies.scan(root)
        performance = self.performance.scan(root)
        accessibility = self.accessibility.scan(root)
        secrets = self.secrets.audit_project(root)

        requirement = None
        try:
            requirement = self.requirements.assess(
                root,
                spec,
                instruction=instruction or spec.summary,
                pipeline_report=pipeline_report or {},
                trace=trace or {},
            )
        except Exception:
            requirement = None

        blockers: list[str] = []
        warnings: list[str] = []

        if not release.quality_verified:
            blockers.append("quality evidence is not release-ready")
        if not release.all_requested_artifacts_ready:
            blockers.append("one or more requested artifacts are not ready")
        for row in dependency.findings:
            if row.severity == "high":
                blockers.append(f"dependency: {row.dependency}: {row.reason}")
            else:
                warnings.append(f"dependency: {row.dependency}: {row.reason}")
        for row in accessibility.issues:
            if row.severity == "high":
                blockers.append(f"accessibility: {row.rule}")
            else:
                warnings.append(f"accessibility: {row.rule}")
        for row in performance.findings:
            warnings.append(f"performance: {row.metric} exceeds budget")
        if not secrets.safe:
            blockers.extend(f"secrets: {x}" for x in secrets.findings)
        if requirement is not None:
            if requirement.structural_blockers:
                blockers.extend(f"requirement: {x}" for x in requirement.structural_blockers)
            if requirement.semantic_review_required:
                warnings.append("requirement coverage still requires semantic review")

        return ReleaseGuardianReport(
            status="blocked" if blockers else "approval_required",
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=tuple(dict.fromkeys(warnings)),
            release=release.to_dict(),
            dependency=dependency.to_dict(),
            performance=performance.to_dict(),
            accessibility=accessibility.to_dict(),
            secrets=secrets.to_dict(),
            requirement=requirement.to_dict() if requirement is not None else None,
        )

    @staticmethod
    def save(project_dir: Path, report: ReleaseGuardianReport) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "release_guardian.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
