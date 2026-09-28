from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json
import re


@dataclass(frozen=True)
class DependencyFinding:
    ecosystem: str
    dependency: str
    severity: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DependencyReport:
    status: str
    dependency_count: int
    findings: tuple[DependencyFinding, ...]
    online_vulnerability_check_performed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dependency_count": self.dependency_count,
            "findings": [x.to_dict() for x in self.findings],
            "online_vulnerability_check_performed": self.online_vulnerability_check_performed,
        }


class DependencyGuardian:
    """Offline dependency hygiene checks. It never claims CVE freshness without a live advisory source."""

    def scan(self, project_dir: Path) -> DependencyReport:
        root = Path(project_dir)
        findings: list[DependencyFinding] = []
        count = 0

        requirements = root / "requirements.txt"
        if requirements.is_file():
            for raw in requirements.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                count += 1
                name = re.split(r"[<>=!~\[]", line, maxsplit=1)[0].strip()
                if "==" not in line and "@" not in line:
                    findings.append(DependencyFinding(
                        "python", name or line, "medium",
                        "dependency is not exactly pinned",
                    ))
                if line.startswith(("-e ", "git+", "http://", "https://")):
                    findings.append(DependencyFinding(
                        "python", name or line, "medium",
                        "dependency uses a mutable or remote source",
                    ))

        package = root / "package.json"
        if package.is_file():
            try:
                data = json.loads(package.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            for section in ("dependencies", "devDependencies"):
                deps = data.get(section) if isinstance(data.get(section), dict) else {}
                for name, version in deps.items():
                    count += 1
                    value = str(version).strip()
                    if value in {"", "*", "latest"}:
                        findings.append(DependencyFinding(
                            "npm", str(name), "high",
                            f"dependency uses unsafe floating version '{value or '<empty>'}'",
                        ))
                    elif value.startswith(("git+", "http:", "https:", "file:")):
                        findings.append(DependencyFinding(
                            "npm", str(name), "medium",
                            "dependency uses a remote or local mutable source",
                        ))

        status = "attention_required" if findings else "pass"
        return DependencyReport(
            status=status,
            dependency_count=count,
            findings=tuple(findings),
            online_vulnerability_check_performed=False,
        )

    @staticmethod
    def save(project_dir: Path, report: DependencyReport) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "dependency_guardian.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
