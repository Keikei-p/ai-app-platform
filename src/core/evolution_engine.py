from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
import json

from .evaluation_engine import EvaluationEngine, EvaluationReport


ROOT_POLICY_PATHS = {
    "src/core/safety.py",
    "src/core/permissions.py",
    "src/core/approval.py",
    "src/core/agent_tools.py",
    "src/core/agent_runtime.py",
    "src/tools/security_selfcheck.py",
}

ROOT_POLICY_PREFIXES = (
    ".github/workflows/",
)

FORBIDDEN_AUTONOMOUS_ACTIONS = {
    "merge_main",
    "push_main",
    "publish_release",
    "production_deploy",
    "store_submit",
    "billing_change",
    "credential_export",
    "disable_safety",
    "disable_tests",
    "disable_approval",
}


@dataclass(frozen=True)
class EvolutionPolicy:
    minimum_score_delta: int = 1
    require_all_quality_gates: bool = True
    require_evidence: bool = True
    human_review_required: bool = True
    auto_apply: bool = False
    auto_merge_main: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvolutionDecision:
    status: str
    eligible: bool
    baseline_score: int
    candidate_score: int
    score_delta: int
    critical_regression: bool
    protected_changes: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    changed_paths: tuple[str, ...]
    policy: EvolutionPolicy
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["protected_changes"] = list(self.protected_changes)
        data["evidence_refs"] = list(self.evidence_refs)
        data["blockers"] = list(self.blockers)
        data["changed_paths"] = list(self.changed_paths)
        data["policy"] = self.policy.to_dict()
        return data


class VerifiedEvolutionEngine:
    """Evidence-based gate for Aivy self-improvement candidates.

    This engine only compares evidence and determines whether a candidate may be
    shown to a human for review. It never edits source code, executes arbitrary
    commands, merges branches, publishes releases, or weakens root policy.
    """

    def __init__(
        self,
        *,
        evaluation: EvaluationEngine | None = None,
        policy: EvolutionPolicy | None = None,
    ):
        self.evaluation = evaluation or EvaluationEngine()
        self.policy = policy or EvolutionPolicy()

    def compare(
        self,
        baseline: EvaluationReport,
        candidate: EvaluationReport,
        *,
        changed_paths: list[str] | tuple[str, ...],
        evidence_refs: list[str] | tuple[str, ...],
        requested_actions: list[str] | tuple[str, ...] = (),
    ) -> EvolutionDecision:
        paths = tuple(dict.fromkeys(self._normalize_path(x) for x in changed_paths if str(x).strip()))
        evidence = tuple(dict.fromkeys(str(x).strip() for x in evidence_refs if str(x).strip()))
        actions = tuple(dict.fromkeys(str(x).strip() for x in requested_actions if str(x).strip()))

        comparison = self.evaluation.compare(baseline, candidate)
        protected = tuple(path for path in paths if self._protected(path))
        blockers: list[str] = []

        if protected:
            blockers.append("candidate modifies immutable root policy or CI safety files")

        forbidden_actions = [x for x in actions if x in FORBIDDEN_AUTONOMOUS_ACTIONS]
        if forbidden_actions:
            blockers.append("candidate requests forbidden autonomous action: " + ", ".join(forbidden_actions))

        if comparison["critical_regression"]:
            blockers.append("candidate introduces a critical quality regression")

        if self.policy.require_all_quality_gates:
            missing = []
            if not candidate.tests_passed:
                missing.append("tests")
            if not candidate.security_passed:
                missing.append("security")
            if not candidate.design_passed:
                missing.append("design")
            if not candidate.preview_ready:
                missing.append("preview")
            if missing:
                blockers.append("candidate quality gates failed: " + ", ".join(missing))

        if comparison["delta"] < self.policy.minimum_score_delta:
            blockers.append(
                f"candidate score delta {comparison['delta']} is below required +{self.policy.minimum_score_delta}"
            )

        if self.policy.require_evidence and not evidence:
            blockers.append("candidate has no verification evidence")

        if not paths:
            blockers.append("candidate has no declared changed paths")

        eligible = not blockers
        status = "human_review_required" if eligible else "rejected"
        return EvolutionDecision(
            status=status,
            eligible=eligible,
            baseline_score=baseline.score,
            candidate_score=candidate.score,
            score_delta=int(comparison["delta"]),
            critical_regression=bool(comparison["critical_regression"]),
            protected_changes=protected,
            evidence_refs=evidence,
            blockers=tuple(blockers),
            changed_paths=paths,
            policy=self.policy,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def compare_verified_trees(
        self,
        baseline: EvaluationReport,
        candidate: EvaluationReport,
        *,
        baseline_root: Path,
        candidate_root: Path,
        changed_paths: list[str] | tuple[str, ...],
        evidence_refs: list[str] | tuple[str, ...],
        requested_actions: list[str] | tuple[str, ...] = (),
    ) -> EvolutionDecision:
        from .root_policy_guard import RootPolicyGuard

        root_diff = RootPolicyGuard().compare(
            Path(baseline_root),
            Path(candidate_root),
        )
        actual_paths = list(dict.fromkeys([
            *(str(x) for x in changed_paths),
            *root_diff.changed_paths,
        ]))
        return self.compare(
            baseline,
            candidate,
            changed_paths=actual_paths,
            evidence_refs=evidence_refs,
            requested_actions=requested_actions,
        )

    def compare_project_reports(
        self,
        baseline_project_dir: Path,
        candidate_project_dir: Path,
        *,
        changed_paths: list[str] | tuple[str, ...],
        evidence_refs: list[str] | tuple[str, ...],
        requested_actions: list[str] | tuple[str, ...] = (),
    ) -> EvolutionDecision:
        baseline = self.evaluation.evaluate(Path(baseline_project_dir))
        candidate = self.evaluation.evaluate(Path(candidate_project_dir))
        return self.compare(
            baseline,
            candidate,
            changed_paths=changed_paths,
            evidence_refs=evidence_refs,
            requested_actions=requested_actions,
        )

    @staticmethod
    def report_from_dict(data: dict[str, Any]) -> EvaluationReport:
        if not isinstance(data, dict):
            raise ValueError("evaluation report must be an object")
        required = (
            "score",
            "tests_passed",
            "test_pass_ratio",
            "design_passed",
            "design_score",
            "security_passed",
            "preview_ready",
            "release_ready",
            "artifact_count",
            "learning_eligible",
        )
        missing = [x for x in required if x not in data]
        if missing:
            raise ValueError("evaluation report missing: " + ", ".join(missing))
        return EvaluationReport(
            score=max(0, min(100, int(data["score"]))),
            tests_passed=bool(data["tests_passed"]),
            test_pass_ratio=max(0.0, min(1.0, float(data["test_pass_ratio"]))),
            design_passed=bool(data["design_passed"]),
            design_score=max(0, min(100, int(data["design_score"]))),
            security_passed=bool(data["security_passed"]),
            preview_ready=bool(data["preview_ready"]),
            release_ready=bool(data["release_ready"]),
            artifact_count=max(0, int(data["artifact_count"])),
            learning_eligible=bool(data["learning_eligible"]),
            regressions=tuple(str(x) for x in data.get("regressions") or ()),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
        )

    def save(self, project_dir: Path, decision: EvolutionDecision) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "evolution_decision.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(decision.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _normalize_path(value: str) -> str:
        raw = str(value).replace("\\", "/").strip().lstrip("/")
        pure = PurePosixPath(raw)
        if ".." in pure.parts:
            raise ValueError("evolution candidate path traversal is not allowed")
        return pure.as_posix()

    @staticmethod
    def _protected(path: str) -> bool:
        if path in ROOT_POLICY_PATHS:
            return True
        return any(path.startswith(prefix) for prefix in ROOT_POLICY_PREFIXES)
