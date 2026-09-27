from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json


@dataclass(frozen=True)
class EvaluationReport:
    score: int
    tests_passed: bool
    test_pass_ratio: float
    design_passed: bool
    design_score: int
    security_passed: bool
    preview_ready: bool
    release_ready: bool
    artifact_count: int
    learning_eligible: bool
    regressions: tuple[str, ...]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["regressions"] = list(self.regressions)
        return data


class EvaluationEngine:
    """Objective post-run scoring for comparing verified development outcomes."""

    def evaluate(self, project_dir: Path) -> EvaluationReport:
        project_dir = Path(project_dir)
        report_dir = project_dir / ".aiapp" / "reports"
        tests = self._json(report_dir / "test_report.json")
        security = self._json(report_dir / "security_report.json")
        readiness = self._json(report_dir / "build_readiness.json")
        design = self._json(project_dir / "design_review.json")

        results = tests.get("results") if isinstance(tests.get("results"), list) else []
        passed_count = sum(1 for x in results if isinstance(x, dict) and x.get("passed") is True)
        ratio = passed_count / len(results) if results else 0.0
        tests_passed = bool(tests.get("passed")) and bool(results)
        design_score = int(design.get("score") or 0)
        design_passed = bool(design.get("passed"))
        security_passed = bool(security.get("passed"))
        preview_ready = bool(readiness.get("preview_ready"))
        release_ready = bool(readiness.get("release_ready"))
        artifacts = [
            p for p in (project_dir / "artifacts").rglob("*")
            if p.is_file() and not p.is_symlink()
        ] if (project_dir / "artifacts").is_dir() else []

        score = 0.0
        score += ratio * 30
        score += 25 if security_passed else 0
        score += max(0, min(20, design_score * 0.20))
        score += 15 if preview_ready else 0
        score += 5 if release_ready else 0
        score += 5 if artifacts else 0
        final_score = max(0, min(100, round(score)))

        regressions: list[str] = []
        if not tests_passed:
            regressions.append("tests")
        if not security_passed:
            regressions.append("security")
        if not design_passed:
            regressions.append("design")
        if not preview_ready:
            regressions.append("preview")

        learning_eligible = tests_passed and security_passed and design_passed and preview_ready
        return EvaluationReport(
            score=final_score,
            tests_passed=tests_passed,
            test_pass_ratio=round(ratio, 4),
            design_passed=design_passed,
            design_score=design_score,
            security_passed=security_passed,
            preview_ready=preview_ready,
            release_ready=release_ready,
            artifact_count=len(artifacts),
            learning_eligible=learning_eligible,
            regressions=tuple(regressions),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def save(self, project_dir: Path, report: EvaluationReport) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "agent_evaluation.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def compare(before: EvaluationReport, after: EvaluationReport) -> dict[str, Any]:
        critical_regression = (
            (before.tests_passed and not after.tests_passed)
            or (before.security_passed and not after.security_passed)
            or (before.design_passed and not after.design_passed)
            or (before.preview_ready and not after.preview_ready)
        )
        delta = after.score - before.score
        return {
            "score_before": before.score,
            "score_after": after.score,
            "delta": delta,
            "critical_regression": critical_regression,
            "improved": delta > 0 and not critical_regression,
        }

    @staticmethod
    def _json(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
