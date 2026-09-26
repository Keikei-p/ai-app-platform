from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import json
from .safety import SafetyGate, SafetyDecision
from .permissions import PermissionEngine
from .generator import StarterGenerator
from .mobile_generator import MobileGenerator
from .project_manager import ProjectManager
from .planner import IntentPlanner
from .test_runner import ProjectTestRunner, TestResult
from .database import create_job, finish_job, log_event
from .risk_report import ReleaseRiskAssessor
from .code_vault import CodeVault
from .design_ai import DesignAI, DesignReview
from .capability import CapabilityAssessor, CapabilityGap
from .development_memory import DevelopmentMemory

@dataclass
class CoreResult:
    ok: bool
    message: str
    safety: SafetyDecision
    files: list[Path]
    tests: list[TestResult]
    plan: dict | None = None
    risk_items: list[dict] | None = None
    design_review: DesignReview | None = None
    capability_gaps: list[CapabilityGap] | None = None
    lessons_used: list[str] | None = None

class AICore:
    """Local-first orchestration core. Models cannot bypass safety, permissions, tests, approval, or audit."""
    def __init__(self):
        self.safety = SafetyGate()
        self.permissions = PermissionEngine()
        self.generator = StarterGenerator()
        self.mobile = MobileGenerator()
        self.projects = ProjectManager()
        self.planner = IntentPlanner()
        self.tests = ProjectTestRunner()
        self.risk = ReleaseRiskAssessor()
        self.vault = CodeVault()
        self.design = DesignAI()
        self.capability = CapabilityAssessor()
        self.memory = DevelopmentMemory()

    def execute(
        self,
        project_name: str,
        slug: str,
        project_dir: Path,
        instruction: str,
        progress: Callable[[str, str], None] | None = None,
    ) -> CoreResult:
        def emit(stage: str, message: str) -> None:
            if progress is not None:
                try:
                    progress(stage, message)
                except Exception:
                    # Progress reporting must never break the build pipeline.
                    pass

        emit("understand", "内容と安全性を確認しています")
        job_id = create_job(slug, instruction)
        decision = self.safety.check(instruction)
        log_event("safety.checked", json.dumps({"level": decision.level, "reasons": decision.reasons}, ensure_ascii=False), slug, "safety-gate")
        if not decision.allowed:
            msg = f"Safety Gateで停止しました: {', '.join(decision.reasons)}"
            finish_job(job_id, "blocked", msg)
            return CoreResult(False, msg, decision, [], [], None, [], None, [], [])
        if decision.requires_human_review:
            msg = f"高リスク領域のため人による追加確認が必要です: {', '.join(decision.reasons)}"
            finish_job(job_id, "review_required", msg)
            return CoreResult(False, msg, decision, [], [], None, [], None, [], [])

        emit("plan", "要件を整理して設計しています")
        lessons = self.memory.lessons_for(instruction)
        enriched = instruction
        if lessons:
            enriched += "\n過去の改善学習: " + " / ".join(lessons)

        plan = self.planner.plan(project_name, slug, enriched, decision.level)
        emit("build", "アプリのコードと画面を作成しています")
        self.projects.snapshot(slug, "before-ai-change")
        self.vault.save(slug, "AI変更前", actor="ai-core", reason=instruction, kind="auto-before-ai")
        spec_path = plan.spec.save(project_dir)
        files = [spec_path]
        files += self.generator.generate_from_spec(project_dir, plan.spec)
        files += self.mobile.generate(project_dir, plan.spec)

        emit("design", "見やすさと操作性を確認しています")
        design_review = self.design.review(project_dir)
        files.append(self.design.save(project_dir, design_review))
        log_event("design.reviewed", json.dumps(design_review.to_dict(), ensure_ascii=False), slug, "design-ai")

        gaps = self.capability.assess(plan.spec, project_dir)
        files.append(self.capability.save(project_dir, gaps))
        if gaps:
            log_event("capability.gaps", json.dumps([g.__dict__ for g in gaps], ensure_ascii=False), slug, "capability-assessor")

        risk_items = [x.__dict__ for x in self.risk.assess(plan.spec)]
        risk_path = project_dir / "release_risk.json"
        risk_path.write_text(json.dumps({
            "disclaimer": "Automated checklist only; not legal advice or a release guarantee.",
            "items": risk_items,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        files.append(risk_path)
        log_event("risk.assessed", json.dumps(risk_items, ensure_ascii=False), slug, "risk-engine")

        emit("test", "自動テストで動作を確認しています")
        test_results = self.tests.run(project_dir)
        passed = all(t.passed for t in test_results)
        test_summary = [{"name": t.name, "passed": t.passed, "detail": t.detail} for t in test_results]
        log_event("tests.completed", json.dumps(test_summary, ensure_ascii=False), slug, "test-engine")

        # A build may be technically valid but still not be a releasable store binary.
        release_blockers = [g for g in gaps if g.blocking]
        design_ok = design_review.passed
        if passed and design_ok:
            self.vault.save(slug, "AI変更後", actor="ai-core", reason=instruction, kind="auto-after-ai")
            if release_blockers:
                message = "作成と自動テストは完了しました。未完了の外部/ビルド工程があるため、完成ではなく『完成候補』です。"
            else:
                message = "作成・デザイン審査・自動テストに合格しました。完成候補です。"
        elif not design_ok:
            message = "生成は完了しましたが、Design AIの品質基準に未達です。改善が必要です。"
        else:
            message = "生成は完了しましたが、自動テストに失敗しました。完成扱いにはしません。"

        final_ok = passed and design_ok
        emit("done" if final_ok else "issue", "確認が完了しました" if final_ok else "確認が必要な項目があります")
        finish_job(job_id, "completed" if final_ok else "test_failed", message)
        return CoreResult(final_ok, message, decision, files, test_results, plan.to_dict(), risk_items, design_review, gaps, lessons)
