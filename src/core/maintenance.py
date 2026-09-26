from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from .database import save_maintenance_report, log_event

@dataclass(frozen=True)
class MaintenanceFinding:
    severity: str
    code: str
    message: str
    suggested_action: str | None = None
    auto_fix_safe: bool = False

class MaintenanceInspector:
    def inspect_project(self, project_dir: Path) -> list[MaintenanceFinding]:
        findings: list[MaintenanceFinding] = []
        if not project_dir.exists():
            return [MaintenanceFinding("error", "PROJECT_MISSING", "Project directory does not exist.")]
        if not (project_dir / "project.json").exists():
            findings.append(MaintenanceFinding("warning", "META_MISSING", "project.json is missing.", "restore_project_metadata", False))
        if not (project_dir / "app_spec.json").exists():
            findings.append(MaintenanceFinding("warning", "SPEC_MISSING", "app_spec.json is missing.", "regenerate_spec", False))
        if (project_dir / "index.html").exists() and not (project_dir / "styles.css").exists():
            findings.append(MaintenanceFinding("warning", "STYLE_MISSING", "Web project has index.html but no styles.css.", "create_default_styles", True))
        if not findings:
            findings.append(MaintenanceFinding("ok", "BASIC_OK", "Basic local project health check passed."))
        return findings

    def record(self, project_slug: str, findings: list[MaintenanceFinding]) -> None:
        for f in findings:
            save_maintenance_report(project_slug, f.severity, f.code, f.message)
        log_event("maintenance.scan", f"{len(findings)} finding(s)", project_slug, "maintenance-ai")
