from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .agent_runtime import AgentPlan
from .redaction import redact_sensitive


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class BuildTraceStep:
    step_id: str
    action: str
    tool_name: str | None
    status: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BuildExecutionTrace:
    run_id: str
    project_slug: str | None
    status: str
    created_at: str
    steps: tuple[BuildTraceStep, ...]
    history_path: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [x.to_dict() for x in self.steps]
        return data


class BuildExecutionTracer:
    """Map real AICore outcomes back onto the transparent Aivy Agent Plan."""

    def create(self, plan: AgentPlan, core_result: Any, project_dir: Path) -> BuildExecutionTrace:
        pipeline = dict(getattr(core_result, "pipeline_report", None) or {})
        security = dict(pipeline.get("security") or {})
        tests = list(getattr(core_result, "tests", None) or ())
        design = getattr(core_result, "design_review", None)
        repairs = list(getattr(core_result, "repair_attempts", None) or ())
        result_plan = getattr(core_result, "plan", None)

        tests_passed = bool(tests) and all(bool(getattr(x, "passed", False)) for x in tests)
        design_passed = bool(getattr(design, "passed", False)) if design is not None else False
        security_passed = bool(security.get("passed"))
        core_ok = bool(getattr(core_result, "ok", False))

        package_built = any(
            self._built(value)
            for value in (
                getattr(core_result, "windows_build", None),
                getattr(core_result, "web_build", None),
                getattr(core_result, "android_build", None),
                getattr(core_result, "ios_source_build", None),
            )
        )

        rows: list[BuildTraceStep] = []
        for step in plan.steps:
            status, summary = self._step_status(
                step.step_id,
                action=step.action,
                tool_name=step.tool_name,
                core_ok=core_ok,
                has_plan=bool(result_plan),
                tests_passed=tests_passed,
                design_passed=design_passed,
                security_passed=security_passed,
                repairs=repairs,
                package_built=package_built,
            )
            rows.append(BuildTraceStep(
                step.step_id,
                step.action,
                step.tool_name,
                status,
                redact_sensitive(summary)[:1200],
            ))

        overall = "verified" if core_ok and tests_passed and design_passed and security_passed else "blocked"
        relative = f".aiapp/agent/runs/{plan.run_id}-build.json"
        trace = BuildExecutionTrace(
            run_id=plan.run_id,
            project_slug=plan.project_slug,
            status=overall,
            created_at=_now(),
            steps=tuple(rows),
            history_path=relative,
        )
        self.save(Path(project_dir), trace)
        return trace

    @staticmethod
    def _built(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        return bool(value.get("built") or value.get("artifact"))

    @staticmethod
    def _step_status(
        step_id: str,
        *,
        action: str,
        tool_name: str | None,
        core_ok: bool,
        has_plan: bool,
        tests_passed: bool,
        design_passed: bool,
        security_passed: bool,
        repairs: list[dict[str, Any]],
        package_built: bool,
    ) -> tuple[str, str]:
        if step_id == "understand":
            return "completed", "依頼内容をSafety Gateと生成フローへ渡した"
        if step_id == "inspect":
            return "completed", "既存プロジェクト状態と履歴を参照した"
        if step_id == "inspect-knowledge":
            return "completed", "Verified Memory / Knowledgeだけを再利用候補として参照した"
        if step_id == "plan":
            return ("completed", "実装計画を生成した") if has_plan else ("blocked", "実装計画を生成できなかった")
        if step_id == "generate":
            return ("completed", "AICore生成パイプラインを実行した") if has_plan else ("blocked", "生成に到達しなかった")
        if step_id == "validate-tests":
            return ("pass", "自動テストPASS") if tests_passed else ("fail", "自動テストNG")
        if step_id == "validate-design":
            return ("pass", "Design AI PASS") if design_passed else ("fail", "Design AI NG")
        if step_id == "validate-security":
            return ("pass", "Security Gate PASS") if security_passed else ("fail", "Security Gate NG")
        if step_id == "repair":
            if repairs:
                repaired = any(bool(x.get("preview_ready")) for x in repairs if isinstance(x, dict))
                return ("completed", "自動修正を実行し品質Gateを再確認した") if repaired else ("blocked", "自動修正後も未解決項目が残った")
            return ("not_needed", "品質Gateで修正不要だった")
        if step_id == "package":
            if not core_ok:
                return "blocked", "品質Gate未通過のため成果物準備を完了扱いにしない"
            return ("completed", "実成果物を生成した") if package_built else ("pending", "対象環境依存の成果物は準備中または対象外")
        if step_id == "review":
            if core_ok:
                return "approval_required", "外部公開・署名・ストア提出は人の明示承認待ち"
            return "blocked", "品質Gate未通過のため公開確認へ進めない"
        if step_id == "report":
            return ("verified", "独立Evidenceを伴う生成結果を報告可能") if core_ok else ("blocked", "未解決の品質項目があるため完成報告不可")
        return "planned", f"{action} / {tool_name or 'no-tool'}"

    @staticmethod
    def save(project_dir: Path, trace: BuildExecutionTrace) -> Path:
        target = Path(project_dir) / trace.history_path
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = trace.to_dict()
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
        return target
