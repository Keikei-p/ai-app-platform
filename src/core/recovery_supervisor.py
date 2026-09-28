from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import re

from .evaluation_engine import EvaluationEngine, EvaluationReport


FAILURE_KINDS = {
    "TEST",
    "SECURITY",
    "UI",
    "BUILD",
    "DEPENDENCY",
    "ENVIRONMENT",
    "CODE",
    "CAPABILITY",
    "UNKNOWN",
}


@dataclass(frozen=True)
class FailureClassification:
    kind: str
    retryable: bool
    fingerprint: str
    signals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["signals"] = list(self.signals)
        return data


@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    reason: str
    attempts_used: int
    max_attempts: int
    repeated_failure: bool
    baseline_score: int
    candidate_score: int
    score_delta: int
    critical_regression: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IndependentReview:
    approved: bool
    status: str
    findings: tuple[str, ...]
    checks: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["findings"] = list(self.findings)
        return data


@dataclass(frozen=True)
class LearningDecision:
    status: str
    promote: bool
    reason: str
    lesson: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RecoverySupervisor:
    """Deterministic guard around Aivy's bounded repair loop.

    AICore already performs at most two bounded coding-brain repair attempts.
    This supervisor independently classifies failures, detects repeated outcomes,
    compares verified before/after quality, requests recovery on regression,
    performs a second-pass deterministic review, and decides whether a lesson is
    safe to promote into verified development memory.

    It never edits application source, executes commands, bypasses approval, or
    publishes externally.
    """

    MAX_REPAIR_ATTEMPTS = 2

    def __init__(self, evaluation: EvaluationEngine | None = None):
        self.evaluation = evaluation or EvaluationEngine()

    def capture(self, project_dir: Path) -> EvaluationReport:
        return self.evaluation.evaluate(Path(project_dir))

    def classify(
        self,
        pipeline_report: dict[str, Any] | None,
        repair_attempts: list[dict[str, Any]] | None = None,
    ) -> FailureClassification:
        report = dict(pipeline_report or {})
        attempts = list(repair_attempts or [])
        reasons = [str(x) for x in report.get("blocking_reasons") or []]
        signals: list[str] = []

        tests = report.get("test_results")
        if isinstance(tests, list):
            for row in tests:
                if isinstance(row, dict) and row.get("passed") is False:
                    signals.append("test:" + str(row.get("name") or "unknown")[:160])

        security = report.get("security")
        if isinstance(security, dict):
            for row in security.get("findings") or []:
                if isinstance(row, dict) and row.get("blocking", True):
                    signals.append("security:" + str(row.get("key") or "finding")[:160])

        for reason in reasons:
            signals.append("reason:" + reason[:160])

        for row in attempts[-self.MAX_REPAIR_ATTEMPTS :]:
            if not isinstance(row, dict):
                continue
            coding = row.get("coding")
            if isinstance(coding, dict):
                summary = str(coding.get("summary") or "")
                if summary:
                    signals.append("repair:" + self._normalize(summary)[:160])

        hay = " ".join(reasons + signals).lower()
        if "security_gate_failed" in hay or "security:" in hay or "secret" in hay:
            kind = "SECURITY"
            retryable = False
        elif "automated_tests_failed" in hay or "test:" in hay:
            kind = "TEST"
            retryable = True
        elif "design_gate_failed" in hay or "design" in hay or "responsive" in hay:
            kind = "UI"
            retryable = True
        elif "dependency" in hay or "module not found" in hay or "modulenotfound" in hay:
            kind = "DEPENDENCY"
            retryable = True
        elif "environment" in hay or "permission denied" in hay or "not installed" in hay:
            kind = "ENVIRONMENT"
            retryable = False
        elif "build" in hay or "compile" in hay or "bundle" in hay:
            kind = "BUILD"
            retryable = True
        elif "capability_gaps" in hay or "capability" in hay:
            kind = "CAPABILITY"
            retryable = False
        elif "syntax" in hay or "typeerror" in hay or "valueerror" in hay or "code" in hay:
            kind = "CODE"
            retryable = True
        else:
            kind = "UNKNOWN"
            retryable = False

        normalized = sorted(set(self._normalize(x) for x in signals if x.strip()))
        payload = json.dumps({"kind": kind, "signals": normalized}, ensure_ascii=False, sort_keys=True)
        fingerprint = sha256(payload.encode("utf-8")).hexdigest()
        return FailureClassification(kind, retryable, fingerprint, tuple(normalized))

    def decide(
        self,
        baseline: EvaluationReport,
        candidate: EvaluationReport,
        *,
        repair_attempts: list[dict[str, Any]] | None,
        classification: FailureClassification,
    ) -> RecoveryDecision:
        attempts = list(repair_attempts or [])
        comparison = self.evaluation.compare(baseline, candidate)
        fingerprints = self._attempt_fingerprints(attempts)
        repeated = len(fingerprints) >= 2 and fingerprints[-1] == fingerprints[-2]

        if comparison["critical_regression"] or candidate.score < baseline.score:
            action = "recover"
            reason = "candidate is worse than the verified baseline"
        elif not attempts and classification.kind == "UNKNOWN" and not classification.signals:
            action = "accept"
            reason = "no repair outcome exists; completion gates remain authoritative"
        elif candidate.learning_eligible and candidate.preview_ready:
            action = "accept"
            reason = "all quality gates pass without a critical regression"
        elif repeated:
            action = "stop"
            reason = "the same failure repeated across consecutive repair attempts"
        elif len(attempts) >= self.MAX_REPAIR_ATTEMPTS:
            action = "stop"
            reason = "bounded repair-attempt budget is exhausted"
        elif classification.retryable:
            action = "retry"
            reason = "failure is classified as locally repairable within the remaining budget"
        else:
            action = "stop"
            reason = "failure needs evidence or human/environment intervention"

        return RecoveryDecision(
            action=action,
            reason=reason,
            attempts_used=len(attempts),
            max_attempts=self.MAX_REPAIR_ATTEMPTS,
            repeated_failure=repeated,
            baseline_score=baseline.score,
            candidate_score=candidate.score,
            score_delta=int(comparison["delta"]),
            critical_regression=bool(comparison["critical_regression"]),
        )

    def independent_review(
        self,
        baseline: EvaluationReport,
        candidate: EvaluationReport,
        decision: RecoveryDecision,
        *,
        postflight_ok: bool,
    ) -> IndependentReview:
        if decision.attempts_used == 0:
            checks = {
                "postflight": bool(postflight_ok),
                "no_critical_regression": not decision.critical_regression,
                "not_worse_than_baseline": candidate.score >= baseline.score,
                "repair_budget_respected": True,
            }
        else:
            checks = {
                "tests": candidate.tests_passed,
                "security": candidate.security_passed,
                "design": candidate.design_passed,
                "preview": candidate.preview_ready,
                "postflight": bool(postflight_ok),
                "no_critical_regression": not decision.critical_regression,
                "not_worse_than_baseline": candidate.score >= baseline.score,
                "repair_budget_respected": decision.attempts_used <= decision.max_attempts,
            }
        findings = [name for name, passed in checks.items() if not passed]
        if decision.action != "accept":
            findings.append("recovery_decision:" + decision.action)
        approved = not findings
        return IndependentReview(
            approved=approved,
            status="approved" if approved else "changes_required",
            findings=tuple(findings),
            checks=checks,
        )

    def learning_decision(
        self,
        *,
        classification: FailureClassification,
        decision: RecoveryDecision,
        review: IndependentReview,
        certificate_verified: bool,
        evidence_refs: list[str] | tuple[str, ...],
    ) -> LearningDecision:
        evidence = [str(x).strip() for x in evidence_refs if str(x).strip()]
        if decision.attempts_used <= 0:
            return LearningDecision("not_applicable", False, "no repair attempt occurred", "")
        if not review.approved:
            return LearningDecision("rejected", False, "independent review did not approve the result", "")
        if not certificate_verified:
            return LearningDecision("rejected", False, "development certificate is not verified", "")
        if decision.action != "accept":
            return LearningDecision("rejected", False, "recovery decision is not accept", "")
        if not evidence:
            return LearningDecision("rejected", False, "verified evidence references are required", "")
        lesson = (
            f"Verified {classification.kind.lower()} recovery: "
            f"{decision.attempts_used} bounded repair attempt(s) ended with all quality gates passing "
            f"and score delta {decision.score_delta:+d}."
        )
        return LearningDecision("verified", True, "review and certificate evidence permit promotion", lesson)

    def save(
        self,
        project_dir: Path,
        *,
        baseline: EvaluationReport,
        candidate: EvaluationReport,
        classification: FailureClassification,
        decision: RecoveryDecision,
        review: IndependentReview | None = None,
        learning: LearningDecision | None = None,
    ) -> Path:
        path = Path(project_dir) / ".aiapp" / "reports" / "recovery_supervision.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "baseline": baseline.to_dict(),
            "candidate": candidate.to_dict(),
            "classification": classification.to_dict(),
            "decision": decision.to_dict(),
            "review": review.to_dict() if review else None,
            "learning": learning.to_dict() if learning else None,
            "policy": {
                "max_repair_attempts": self.MAX_REPAIR_ATTEMPTS,
                "arbitrary_shell": False,
                "automatic_external_actions": False,
                "automatic_main_merge": False,
                "verified_learning_only": True,
            },
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    @classmethod
    def _attempt_fingerprints(cls, attempts: list[dict[str, Any]]) -> list[str]:
        rows: list[str] = []
        for item in attempts:
            if not isinstance(item, dict):
                continue
            reasons = item.get("blocking_reasons")
            if not isinstance(reasons, list):
                reasons = []
            coding = item.get("coding")
            status = str(coding.get("status") or "") if isinstance(coding, dict) else ""
            payload = json.dumps(
                {
                    "reasons": sorted(cls._normalize(str(x)) for x in reasons),
                    "coding_status": cls._normalize(status),
                    "preview_ready": bool(item.get("preview_ready")),
                },
                sort_keys=True,
            )
            rows.append(sha256(payload.encode("utf-8")).hexdigest())
        return rows

    @staticmethod
    def _normalize(value: str) -> str:
        text = re.sub(r"\s+", " ", str(value).strip().lower())
        return text[:1000]
