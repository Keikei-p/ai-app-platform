from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .evaluation_engine import EvaluationEngine, EvaluationReport


@dataclass(frozen=True)
class CandidateResult:
    candidate_id: str
    score: int
    eligible: bool
    critical_regression: bool
    blockers: tuple[str, ...]
    evaluation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blockers"] = list(self.blockers)
        return data


@dataclass(frozen=True)
class ArenaReport:
    status: str
    winner_id: str | None
    baseline_score: int
    candidates: tuple[CandidateResult, ...]
    created_at: str
    auto_apply: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "winner_id": self.winner_id,
            "baseline_score": self.baseline_score,
            "candidates": [x.to_dict() for x in self.candidates],
            "created_at": self.created_at,
            "auto_apply": self.auto_apply,
        }


class CandidateArena:
    """Evidence-only comparison arena. It never applies a candidate automatically."""

    def __init__(self, evaluation: EvaluationEngine | None = None):
        self.evaluation = evaluation or EvaluationEngine()

    def compare_reports(
        self,
        baseline: EvaluationReport,
        candidates: dict[str, EvaluationReport],
    ) -> ArenaReport:
        rows: list[CandidateResult] = []
        for candidate_id, report in candidates.items():
            comparison = self.evaluation.compare(baseline, report)
            blockers: list[str] = []
            if comparison["critical_regression"]:
                blockers.append("critical quality regression")
            if not report.tests_passed:
                blockers.append("tests failed")
            if not report.security_passed:
                blockers.append("security failed")
            if not report.design_passed:
                blockers.append("design failed")
            if not report.preview_ready:
                blockers.append("preview not ready")
            if report.score <= baseline.score:
                blockers.append("candidate does not improve baseline score")
            rows.append(CandidateResult(
                candidate_id=str(candidate_id),
                score=int(report.score),
                eligible=not blockers,
                critical_regression=bool(comparison["critical_regression"]),
                blockers=tuple(blockers),
                evaluation=report.to_dict(),
            ))

        eligible = [x for x in rows if x.eligible]
        eligible.sort(key=lambda x: (-x.score, x.candidate_id))
        winner = eligible[0].candidate_id if eligible else None
        return ArenaReport(
            status="human_review_required" if winner else "no_eligible_candidate",
            winner_id=winner,
            baseline_score=int(baseline.score),
            candidates=tuple(sorted(rows, key=lambda x: (-x.score, x.candidate_id))),
            created_at=datetime.now(timezone.utc).isoformat(),
            auto_apply=False,
        )

    def compare_directories(
        self,
        baseline_dir: Path,
        candidates: dict[str, Path],
    ) -> ArenaReport:
        baseline = self.evaluation.evaluate(Path(baseline_dir))
        reports = {
            str(candidate_id): self.evaluation.evaluate(Path(path))
            for candidate_id, path in candidates.items()
        }
        return self.compare_reports(baseline, reports)

    @staticmethod
    def save(project_dir: Path, report: ArenaReport) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "candidate_arena.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
