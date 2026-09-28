from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .evaluation_engine import EvaluationReport


@dataclass(frozen=True)
class RegressionReport:
    status: str
    score_before: int
    score_after: int
    score_delta: int
    critical_regressions: tuple[str, ...]
    warnings: tuple[str, ...]
    blocked: bool
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["critical_regressions"] = list(self.critical_regressions)
        data["warnings"] = list(self.warnings)
        return data


class RegressionGuardian:
    """Blocks completion when a previously passing critical gate regresses."""

    CRITICAL = (
        ("tests", "tests_passed"),
        ("security", "security_passed"),
        ("design", "design_passed"),
        ("preview", "preview_ready"),
    )

    def compare(self, before: EvaluationReport, after: EvaluationReport) -> RegressionReport:
        critical = [
            label for label, attr in self.CRITICAL
            if bool(getattr(before, attr)) and not bool(getattr(after, attr))
        ]
        warnings: list[str] = []
        delta = int(after.score) - int(before.score)
        if before.score > 0 and delta < 0:
            warnings.append(f"quality score dropped by {abs(delta)} point(s)")
        if before.release_ready and not after.release_ready:
            warnings.append("release readiness regressed")
        if before.artifact_count > after.artifact_count:
            warnings.append("verified artifact count decreased")
        blocked = bool(critical)
        return RegressionReport(
            status="blocked" if blocked else "pass",
            score_before=int(before.score),
            score_after=int(after.score),
            score_delta=delta,
            critical_regressions=tuple(critical),
            warnings=tuple(warnings),
            blocked=blocked,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def save(project_dir: Path, report: RegressionReport) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "regression_guardian.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
