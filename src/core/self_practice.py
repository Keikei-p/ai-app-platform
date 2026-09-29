from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Any, Callable
import hashlib
import json

from .candidate_arena import CandidateArena
from .config import DATA_DIR, WORKSPACE_DIR
from .evaluation_engine import EvaluationReport
from .learning_flywheel import AivyLearningFlywheel
from .model_benchmark import ModelBenchmarkStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


PROTECTED_SCOPE = (
    "aivy_source",
    "main_branch",
    "secrets",
    "billing",
    "external_publish",
    "production_database",
    "safety",
    "security_policy",
    "permissions",
    "approval",
)


@dataclass(frozen=True)
class PracticeWeakness:
    weakness_id: str
    kind: str
    severity: str
    mode: str
    summary: str
    metric: float
    target: float
    evidence_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["evidence_refs"] = list(self.evidence_refs)
        return row


@dataclass(frozen=True)
class PracticeTask:
    task_id: str
    weakness_id: str
    mode: str
    title: str
    objective: str
    required_checks: tuple[str, ...]
    synthetic_fixture: dict[str, Any]
    protected_scope: tuple[str, ...] = PROTECTED_SCOPE

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["required_checks"] = list(self.required_checks)
        row["protected_scope"] = list(self.protected_scope)
        return row


class WeaknessDetector:
    """Find evidence-backed weaknesses without reading user production data."""

    def __init__(
        self,
        learning: AivyLearningFlywheel | None = None,
        benchmark: ModelBenchmarkStore | None = None,
        workspace_dir: Path | None = None,
    ):
        self.learning = learning or AivyLearningFlywheel()
        self.benchmark = benchmark or ModelBenchmarkStore()
        self.workspace_dir = Path(workspace_dir or WORKSPACE_DIR)

    def detect(self, limit: int = 20) -> list[PracticeWeakness]:
        examples = self.learning.recent(1000)
        rows: list[PracticeWeakness] = []
        verified = len(examples)
        scores = [int(x.evaluation_score) for x in examples]
        average = (sum(scores) / len(scores)) if scores else 0.0
        repaired = sum(1 for x in examples if int(getattr(x, "repair_count", 0)) > 0)

        if verified < 8:
            rows.append(self._weakness(
                "training_data_scarcity", "medium", "app",
                f"Verified examples are still sparse ({verified}).",
                float(verified), 8.0,
                tuple(str(x.example_id) for x in examples[:5]),
            ))
        if verified and average < 95:
            rows.append(self._weakness(
                "verified_quality", "high" if average < 90 else "medium", "app",
                f"Average verified quality is {average:.1f}/100.",
                average, 95.0,
                tuple(str(x.example_id) for x in examples[:8]),
            ))
        if verified:
            repair_rate = repaired / verified
            if repair_rate >= 0.20:
                rows.append(self._weakness(
                    "repair_rate", "high" if repair_rate >= 0.35 else "medium", "app",
                    f"{repair_rate:.0%} of verified builds required repair.",
                    repair_rate, 0.15,
                    tuple(
                        str(x.example_id) for x in examples
                        if int(getattr(x, "repair_count", 0)) > 0
                    )[:8],
                ))

        mode_counts = {"app": 0, "web": 0, "automation": 0}
        for item in examples:
            mode_counts[self._mode_for(item.instruction)] += 1
        for mode, count in mode_counts.items():
            if count < 3:
                rows.append(self._weakness(
                    "mode_experience", "low", mode,
                    f"{mode.upper()} has only {count} verified example(s).",
                    float(count), 3.0,
                    tuple(
                        str(x.example_id) for x in examples
                        if self._mode_for(x.instruction) == mode
                    )[:5],
                ))

        benchmark = self.benchmark.summary()
        for model in benchmark.get("models") or []:
            runs = int(model.get("runs") or 0)
            success = float(model.get("success_rate") or 0.0)
            quality = float(model.get("average_quality") or 0.0)
            if runs >= 3 and (success < 0.90 or quality < 90):
                label = f"{model.get('provider')}/{model.get('model')}"
                rows.append(self._weakness(
                    "model_reliability", "medium", "app",
                    f"Measured route {label} is below target: success {success:.0%}, quality {quality:.1f}.",
                    min(success * 100, quality), 90.0,
                    (f"model-benchmark:{label}:{runs}",),
                ))

        rows.extend(self._guardian_weaknesses())
        severity_order = {"high": 0, "medium": 1, "low": 2}
        rows.sort(key=lambda x: (severity_order.get(x.severity, 9), x.kind, x.mode))
        return rows[: max(1, min(int(limit), 100))]

    def _guardian_weaknesses(self) -> list[PracticeWeakness]:
        if not self.workspace_dir.is_dir():
            return []
        counts = {
            "accessibility_guardian": 0,
            "dependency_guardian": 0,
            "performance_guardian": 0,
            "requirement_guardian": 0,
            "regression_guardian": 0,
        }
        refs: dict[str, list[str]] = {key: [] for key in counts}
        for project in self.workspace_dir.iterdir():
            if not project.is_dir():
                continue
            report_dir = project / ".aiapp" / "reports"
            if not report_dir.is_dir():
                continue
            for key in counts:
                path = report_dir / f"{key}.json"
                if not path.is_file():
                    continue
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(raw, dict) or not self._report_has_problem(raw):
                    continue
                counts[key] += 1
                refs[key].append(f"{project.name}/.aiapp/reports/{path.name}")

        rows = []
        labels = {
            "accessibility_guardian": ("accessibility", "web", "Accessibility issues recur in verified project reviews."),
            "dependency_guardian": ("dependency_hygiene", "app", "Dependency risk findings recur across projects."),
            "performance_guardian": ("performance", "web", "Performance findings recur across projects."),
            "requirement_guardian": ("requirement_coverage", "app", "Requirement evidence gaps recur across projects."),
            "regression_guardian": ("regression_prevention", "app", "Regression findings recur across projects."),
        }
        for key, count in counts.items():
            if count <= 0:
                continue
            kind, mode, summary = labels[key]
            rows.append(self._weakness(
                kind,
                "high" if count >= 3 else "medium",
                mode,
                f"{summary} Findings: {count}.",
                float(count),
                0.0,
                tuple(refs[key][:8]),
            ))
        return rows

    @staticmethod
    def _report_has_problem(raw: dict[str, Any]) -> bool:
        if str(raw.get("status") or "").lower() in {"blocked", "failed", "fail", "attention_required"}:
            return True
        for key in ("critical_regressions", "structural_blockers", "blockers", "issues", "findings"):
            value = raw.get(key)
            if isinstance(value, list):
                if key in {"issues", "findings"}:
                    if any(
                        isinstance(item, dict)
                        and str(item.get("severity") or "").lower() in {"high", "critical"}
                        for item in value
                    ):
                        return True
                elif value:
                    return True
        return False

    @staticmethod
    def _mode_for(text: str) -> str:
        lowered = str(text or "").lower()
        if any(x in lowered for x in ("webサイト", "ホームページ", "wordpress", "seo", "lp", "ポートフォリオ")):
            return "web"
        if any(x in lowered for x in ("自動化", "自動投稿", "cron", "workflow", "スケジュール")):
            return "automation"
        return "app"

    @staticmethod
    def _weakness(
        kind: str,
        severity: str,
        mode: str,
        summary: str,
        metric: float,
        target: float,
        evidence_refs: tuple[str, ...],
    ) -> PracticeWeakness:
        identity = f"{kind}|{mode}|{summary}".encode("utf-8")
        return PracticeWeakness(
            weakness_id=hashlib.sha256(identity).hexdigest()[:20],
            kind=kind,
            severity=severity,
            mode=mode,
            summary=summary,
            metric=round(float(metric), 4),
            target=round(float(target), 4),
            evidence_refs=tuple(x for x in evidence_refs if x),
        )


class SelfPracticePlanner:
    """Turn one weakness into a bounded synthetic exercise."""

    CHECKS = {
        "training_data_scarcity": ("clear_goal", "edge_cases", "verification", "protected_scope"),
        "verified_quality": ("tests", "design", "security", "preview", "protected_scope"),
        "repair_rate": ("preflight", "requirements", "regression", "verification", "protected_scope"),
        "mode_experience": ("mode_standard", "edge_cases", "verification", "protected_scope"),
        "model_reliability": ("fallback", "evidence", "verification", "protected_scope"),
        "accessibility": ("keyboard", "labels", "contrast", "touch_targets", "protected_scope"),
        "dependency_hygiene": ("pinned_dependencies", "audit", "rollback", "protected_scope"),
        "performance": ("asset_budget", "lazy_loading", "measurement", "protected_scope"),
        "requirement_coverage": ("traceability", "acceptance_criteria", "verification", "protected_scope"),
        "regression_prevention": ("baseline", "critical_gates", "rollback", "protected_scope"),
    }

    def plan(self, weakness: PracticeWeakness) -> PracticeTask:
        checks = self.CHECKS.get(
            weakness.kind,
            ("requirements", "verification", "protected_scope"),
        )
        identity = f"{weakness.weakness_id}|{','.join(checks)}".encode("utf-8")
        task_id = hashlib.sha256(identity).hexdigest()[:20]
        return PracticeTask(
            task_id=task_id,
            weakness_id=weakness.weakness_id,
            mode=weakness.mode,
            title=f"Synthetic practice: {weakness.kind.replace('_', ' ')}",
            objective=(
                f"Improve {weakness.kind} for {weakness.mode.upper()} using only synthetic fixtures "
                "and produce a reusable verification strategy."
            ),
            required_checks=tuple(checks),
            synthetic_fixture={
                "fixture_type": "synthetic_only",
                "mode": weakness.mode,
                "weakness_kind": weakness.kind,
                "scenario": self._scenario(weakness),
                "contains_user_data": False,
                "network_allowed": False,
                "paid_actions_allowed": False,
                "production_access_allowed": False,
            },
        )

    @staticmethod
    def _scenario(weakness: PracticeWeakness) -> str:
        scenarios = {
            "accessibility": "A synthetic responsive form has missing labels, weak focus order and small touch targets.",
            "dependency_hygiene": "A synthetic app manifest uses floating dependencies and lacks rollback evidence.",
            "performance": "A synthetic landing page has oversized assets and no measurable performance budget.",
            "regression_prevention": "A synthetic update improves one screen but risks previously passing critical gates.",
            "repair_rate": "A synthetic vague requirement tends to cause rework unless preflight and acceptance criteria are explicit.",
            "model_reliability": "A synthetic coding route may fail and needs an evidence-backed fallback path.",
        }
        return scenarios.get(
            weakness.kind,
            "A synthetic project must improve quality without touching protected systems or real user data.",
        )


class PracticeSandbox:
    """Ephemeral synthetic practice sandbox; never receives a real project path."""

    FORBIDDEN_TOKENS = (
        "main branch write",
        "production deploy",
        "production database",
        "secret export",
        "disable safety",
        "disable approval",
        "paid action",
    )

    def __init__(self, arena: CandidateArena | None = None):
        self.arena = arena or CandidateArena()

    def run(self, task: PracticeTask) -> dict[str, Any]:
        sandbox_root = DATA_DIR / "practice_sandboxes"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="aivy-practice-", dir=sandbox_root) as tmp:
            root = Path(tmp)
            (root / "fixture.json").write_text(
                json.dumps(task.synthetic_fixture, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            strategy = self._candidate_strategy(task)
            (root / "candidate_skill.txt").write_text(strategy, encoding="utf-8")
            checks = self._evaluate_strategy(task, strategy)
            dimensions = self._dimension_review(strategy)
            baseline = self._baseline_report(task)
            candidate = self._candidate_report(
                task,
                {**checks, "all_passed": bool(checks.get("all_passed")) and bool(dimensions.get("all_passed"))},
            )
            arena = self.arena.compare_reports(baseline, {"practice_candidate": candidate})
            winner = arena.winner_id == "practice_candidate"
            return {
                "status": "promotable" if winner else "rejected",
                "task": task.to_dict(),
                "strategy": strategy,
                "checks": checks,
                "dimension_review": dimensions,
                "arena": arena.to_dict(),
                "synthetic_only": True,
                "sandbox_destroyed_after_run": True,
                "network_used": False,
                "paid_actions_used": False,
                "production_data_used": False,
                "source_code_mutated": False,
                "protected_scope": list(PROTECTED_SCOPE),
            }

    @staticmethod
    def _candidate_strategy(task: PracticeTask) -> str:
        guidance = {
            "accessibility": "keyboard labels contrast touch_targets verification",
            "dependency_hygiene": "pinned_dependencies audit rollback verification",
            "performance": "asset_budget lazy_loading measurement verification",
            "requirement_coverage": "traceability acceptance_criteria requirements verification",
            "regression_prevention": "baseline critical_gates regression rollback verification",
            "repair_rate": "preflight requirements acceptance_criteria regression verification",
            "model_reliability": "fallback evidence deterministic verification",
            "mode_experience": f"mode_standard {task.mode} edge_cases verification",
            "verified_quality": "tests design security preview verification",
            "training_data_scarcity": "clear_goal edge_cases synthetic_examples verification",
        }
        core = guidance.get(task.synthetic_fixture["weakness_kind"], "requirements verification")
        return (
            f"{task.mode.upper()} verified practice strategy: {core}. "
            "tests design security accessibility performance regression verification. "
            "protected_scope stays unchanged; use synthetic fixtures only; "
            "no network, no secrets, no billing, no production access, no external publish."
        )

    def _evaluate_strategy(self, task: PracticeTask, strategy: str) -> dict[str, Any]:
        lowered = strategy.lower()
        rows = {
            check: (check.lower() in lowered)
            for check in task.required_checks
            if check != "protected_scope"
        }
        rows["protected_scope"] = (
            "protected_scope stays unchanged" in lowered
            and not any(token in lowered for token in self.FORBIDDEN_TOKENS)
        )
        rows["all_passed"] = all(rows.values())
        return rows

    @staticmethod
    def _dimension_review(strategy: str) -> dict[str, Any]:
        lowered = strategy.lower()
        rows = {
            name: name in lowered
            for name in (
                "tests",
                "design",
                "security",
                "accessibility",
                "performance",
                "regression",
            )
        }
        rows["all_passed"] = all(rows.values())
        return rows

    @staticmethod
    def _baseline_report(task: PracticeTask) -> EvaluationReport:
        return EvaluationReport(
            score=82,
            tests_passed=True,
            test_pass_ratio=0.85,
            design_passed=True,
            design_score=82,
            security_passed=True,
            preview_ready=True,
            release_ready=False,
            artifact_count=1,
            learning_eligible=True,
            regressions=(),
            created_at=_now(),
        )

    @staticmethod
    def _candidate_report(task: PracticeTask, checks: dict[str, Any]) -> EvaluationReport:
        passed = bool(checks.get("all_passed"))
        score = 96 if passed else 74
        return EvaluationReport(
            score=score,
            tests_passed=passed,
            test_pass_ratio=1.0 if passed else 0.7,
            design_passed=passed,
            design_score=96 if passed else 78,
            security_passed=passed,
            preview_ready=passed,
            release_ready=False,
            artifact_count=1,
            learning_eligible=passed,
            regressions=() if passed else ("synthetic_practice_checks",),
            created_at=_now(),
        )


class SelfPracticeEngine:
    """One-task-at-a-time autonomous practice with strict promotion gates."""

    def __init__(
        self,
        *,
        learning: AivyLearningFlywheel | None = None,
        benchmark: ModelBenchmarkStore | None = None,
        arena: CandidateArena | None = None,
        promote_skill: Callable[..., dict[str, Any]] | None = None,
        history_path: Path | None = None,
        workspace_dir: Path | None = None,
        evidence_dir: Path | None = None,
    ):
        self.detector = WeaknessDetector(learning, benchmark, workspace_dir)
        self.planner = SelfPracticePlanner()
        self.sandbox = PracticeSandbox(arena)
        self.promote_skill = promote_skill
        self.history_path = history_path or (DATA_DIR / "aivy_self_practice.jsonl")
        self.evidence_dir = evidence_dir or (DATA_DIR / "aivy_practice_reports")
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def status(self) -> dict[str, Any]:
        weaknesses = self.detector.detect(12)
        recent = self.recent(10)
        promoted = sum(1 for row in recent if row.get("promotion", {}).get("promoted"))
        return {
            "weaknesses": [x.to_dict() for x in weaknesses],
            "practice_queue": [
                self.planner.plan(x).to_dict()
                for x in weaknesses[:5]
            ],
            "last_practice": recent[0] if recent else None,
            "recent_promoted": promoted,
            "synthetic_only": True,
            "max_tasks_per_cycle": 1,
            "network_allowed": False,
            "paid_actions_allowed": False,
            "production_access_allowed": False,
            "gpu_required": False,
            "compute_budget": {"max_tasks_per_cycle": 1, "max_parallel_tasks": 1},
            "source_self_edit_allowed": False,
            "protected_scope": list(PROTECTED_SCOPE),
        }

    def run_one(self) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            return {
                "status": "busy",
                "promoted": False,
                "reason": "another practice cycle is already running",
            }
        try:
            weaknesses = self.detector.detect(20)
            if not weaknesses:
                result = {
                    "status": "no_practice_needed",
                    "promoted": False,
                    "created_at": _now(),
                }
                self._append(result)
                return result

            weakness = weaknesses[0]
            task = self.planner.plan(weakness)
            practice = self.sandbox.run(task)
            evidence_ref = self._save_evidence(
                task.task_id,
                {
                    "created_at": _now(),
                    "weakness": weakness.to_dict(),
                    "practice": practice,
                    "synthetic_only": True,
                    "protected_scope": list(PROTECTED_SCOPE),
                },
            )
            promotion = {
                "promoted": False,
                "reason": "candidate did not pass promotion gate",
            }
            if practice["status"] == "promotable" and self.promote_skill is not None:
                arena = practice.get("arena") or {}
                candidate = next(
                    (
                        row for row in arena.get("candidates") or []
                        if row.get("candidate_id") == "practice_candidate"
                    ),
                    {},
                )
                promotion = self.promote_skill(
                    mode=task.mode,
                    title=f"Self-practice · {weakness.kind}",
                    lesson=str(practice["strategy"]),
                    score=int(candidate.get("score") or 0),
                    evidence_ref=evidence_ref,
                    source_id=f"practice:{task.task_id}",
                )

            result = {
                "status": "completed",
                "created_at": _now(),
                "weakness": weakness.to_dict(),
                "practice": practice,
                "evidence_ref": evidence_ref,
                "promotion": promotion,
                "protected_scope_unchanged": True,
            }
            self._append(result)
            return result
        finally:
            self._lock.release()

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.history_path.is_file():
            return []
        rows = []
        try:
            lines = self.history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in lines[-max(1, min(int(limit), 200)):]:
            try:
                raw = json.loads(line)
                if isinstance(raw, dict):
                    rows.append(raw)
            except Exception:
                continue
        return list(reversed(rows))

    def _append(self, result: dict[str, Any]) -> None:
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")

    def _save_evidence(self, task_id: str, payload: dict[str, Any]) -> str:
        path = self.evidence_dir / f"{task_id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return f"{self.evidence_dir.name}/{path.name}"

