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
from .generation_pipeline import GenerationPipeline
from .coding_brain import CodingBrain
from .windows_packager import WindowsPackager

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
    pipeline_report: dict | None = None
    ai_enhancement: dict | None = None
    repair_attempts: list[dict] | None = None

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
        self.pipeline = GenerationPipeline()
        self.coding_brain = CodingBrain()
        self.windows_packager = WindowsPackager()

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

        emit("enhance", "AI接続時は要件に合わせてコードを追加改善しています")
        try:
            enhancement = self.coding_brain.enhance(project_dir, plan.spec, enriched)
            files += enhancement.files
            enhancement_dict = enhancement.to_dict()
            log_event(
                "coding_brain.completed",
                json.dumps(enhancement_dict, ensure_ascii=False),
                slug,
                "coding-brain",
            )
        except Exception as exc:
            enhancement_dict = {
                "status": "fallback",
                "summary": f"AIコード生成を安全に中止し、安定テンプレートへフォールバック: {type(exc).__name__}: {exc}",
                "files": [],
            }
            log_event(
                "coding_brain.fallback",
                json.dumps(enhancement_dict, ensure_ascii=False),
                slug,
                "coding-brain",
            )

        emit("package", "対象OSごとのビルド準備を作成しています")
        windows_prep = self.windows_packager.prepare(project_dir, plan.spec)
        if windows_prep.prepared:
            files += windows_prep.files

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

        emit("security", "生成物の秘密情報・危険コード・公開可否を確認しています")
        pipeline_report = self.pipeline.evaluate(
            project_dir=project_dir,
            test_results=test_results,
            design_passed=design_review.passed,
            capability_gaps=gaps,
            risk_items=risk_items,
        )
        pipeline_dict = pipeline_report.to_dict()
        log_event(
            "pipeline.completed",
            json.dumps(pipeline_dict, ensure_ascii=False),
            slug,
            "generation-pipeline",
        )
        files.extend([
            project_dir / ".aiapp" / "reports" / "security_report.json",
            project_dir / ".aiapp" / "reports" / "test_report.json",
            project_dir / ".aiapp" / "reports" / "generated_files_manifest.json",
            project_dir / ".aiapp" / "reports" / "build_readiness.json",
            project_dir / ".aiapp" / "approval_state.json",
        ])

        repair_attempts: list[dict] = []
        for attempt in range(1, 3):
            if pipeline_report.preview_ready:
                break

            feedback = self.pipeline.repair_feedback(
                pipeline_report,
                design_review.findings,
            )
            emit("repair", f"品質エラーを自動修正しています ({attempt}/2)")
            try:
                repair = self.coding_brain.enhance(
                    project_dir,
                    plan.spec,
                    enriched + "\n\n自動品質フィードバック:\n" + feedback,
                )
                repair_info = repair.to_dict()
            except Exception as exc:
                repair_info = {
                    "status": "fallback",
                    "summary": f"自動修正を安全に中止: {type(exc).__name__}: {exc}",
                    "files": [],
                }
                repair_attempts.append({
                    "attempt": attempt,
                    "coding": repair_info,
                    "preview_ready": False,
                    "blocking_reasons": list(pipeline_report.blocking_reasons),
                })
                log_event(
                    "coding_brain.repair_failed",
                    json.dumps(repair_attempts[-1], ensure_ascii=False),
                    slug,
                    "coding-brain",
                )
                break

            if repair.status != "applied":
                repair_attempts.append({
                    "attempt": attempt,
                    "coding": repair_info,
                    "preview_ready": False,
                    "blocking_reasons": list(pipeline_report.blocking_reasons),
                })
                log_event(
                    "coding_brain.repair_skipped",
                    json.dumps(repair_attempts[-1], ensure_ascii=False),
                    slug,
                    "coding-brain",
                )
                break

            files += repair.files
            windows_prep = self.windows_packager.prepare(project_dir, plan.spec)
            if windows_prep.prepared:
                files += windows_prep.files

            design_review = self.design.review(project_dir)
            self.design.save(project_dir, design_review)
            gaps = self.capability.assess(plan.spec, project_dir)
            self.capability.save(project_dir, gaps)
            test_results = self.tests.run(project_dir)
            test_summary = [
                {"name": t.name, "passed": t.passed, "detail": t.detail}
                for t in test_results
            ]
            log_event(
                "tests.repair_completed",
                json.dumps({"attempt": attempt, "results": test_summary}, ensure_ascii=False),
                slug,
                "test-engine",
            )
            pipeline_report = self.pipeline.evaluate(
                project_dir=project_dir,
                test_results=test_results,
                design_passed=design_review.passed,
                capability_gaps=gaps,
                risk_items=risk_items,
            )
            repair_attempts.append({
                "attempt": attempt,
                "coding": repair_info,
                "preview_ready": pipeline_report.preview_ready,
                "blocking_reasons": list(pipeline_report.blocking_reasons),
            })
            log_event(
                "coding_brain.repair_completed",
                json.dumps(repair_attempts[-1], ensure_ascii=False),
                slug,
                "coding-brain",
            )

        pipeline_dict = pipeline_report.to_dict()
        final_ok = pipeline_report.preview_ready
        if final_ok:
            self.vault.save(slug, "AI変更後", actor="ai-core", reason=instruction, kind="auto-after-ai")
            if not pipeline_report.release_ready:
                message = (
                    "生成・デザイン・自動テスト・セキュリティ検査に合格しました。"
                    "プレビュー可能です。外部ビルド/署名など未完了項目があるため、公開前の完成候補です。"
                )
            else:
                message = (
                    "生成・デザイン・自動テスト・セキュリティ検査に合格しました。"
                    "公開操作は引き続き明示承認が必要です。"
                )
        elif not pipeline_report.security.passed:
            message = "生成物のセキュリティ検査で停止しました。危険項目を修正するまでプレビュー/公開候補にしません。"
        elif not design_review.passed:
            message = "生成は完了しましたが、Design AIの品質基準に未達です。改善が必要です。"
        else:
            message = "生成は完了しましたが、自動テストに失敗しました。完成扱いにはしません。"

        emit("done" if final_ok else "issue", "確認が完了しました" if final_ok else "確認が必要な項目があります")
        finish_job(job_id, "completed" if final_ok else "quality_gate_failed", message)
        return CoreResult(
            final_ok,
            message,
            decision,
            files,
            test_results,
            plan.to_dict(),
            risk_items,
            design_review,
            gaps,
            lessons,
            pipeline_dict,
            enhancement_dict,
            repair_attempts,
        )
