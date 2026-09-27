from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import hashlib
import json
import uuid

from .development_memory import DevelopmentMemory
from .database import log_event
from .agent_tools import AgentToolRegistry
from .specialist_agents import SpecialistAgentRegistry
from .model_router import ModelRouter
from .knowledge_store import VerifiedKnowledgeStore


ALLOWED_AGENT_ACTIONS = {
    "understand",
    "inspect",
    "plan",
    "generate",
    "validate",
    "repair",
    "package",
    "review",
    "report",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AgentStep:
    step_id: str
    action: str
    title: str
    purpose: str
    tool_name: str | None = None
    specialists: tuple[str, ...] = ()
    requires_human_approval: bool = False


@dataclass
class AgentPlan:
    run_id: str
    goal: str
    project_slug: str | None
    created_at: str
    steps: list[AgentStep] = field(default_factory=list)
    max_repair_attempts: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "goal": self.goal,
            "project_slug": self.project_slug,
            "created_at": self.created_at,
            "max_repair_attempts": self.max_repair_attempts,
            "steps": [asdict(x) for x in self.steps],
        }


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    run_id: str
    created_at: str
    stage: str
    status: str
    summary: str
    source: str
    sha256: str


class EvidenceLedger:
    """Append-only evidence ledger for agent decisions and outcomes."""

    def __init__(self, project_dir: Path | None = None):
        self.project_dir = Path(project_dir) if project_dir else None
        if self.project_dir:
            self.path = self.project_dir / ".aiapp" / "agent" / "evidence.jsonl"
            self.path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.path = None

    def record(
        self,
        *,
        run_id: str,
        stage: str,
        status: str,
        summary: str,
        source: str,
    ) -> EvidenceRecord:
        if stage not in ALLOWED_AGENT_ACTIONS:
            raise ValueError("unsupported agent evidence stage")
        normalized = json.dumps(
            {
                "run_id": run_id,
                "stage": stage,
                "status": status,
                "summary": summary,
                "source": source,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        record = EvidenceRecord(
            evidence_id=uuid.uuid4().hex,
            run_id=run_id,
            created_at=_now(),
            stage=stage,
            status=status,
            summary=summary,
            source=source,
            sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        )
        if self.path:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        return record

    def recent(self, limit: int = 100) -> list[EvidenceRecord]:
        if not self.path or not self.path.is_file():
            return []
        rows: list[EvidenceRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines()[-max(1, limit):]:
            try:
                rows.append(EvidenceRecord(**json.loads(line)))
            except Exception:
                continue
        return rows


class AgentOrchestrator:
    """Policy-bounded planner for autonomous development workflows.

    It never executes shell commands or bypasses existing approval/security gates.
    It creates a transparent plan which existing platform engines can execute.
    """

    def __init__(
        self,
        memory: DevelopmentMemory | None = None,
        tools: AgentToolRegistry | None = None,
        specialists: SpecialistAgentRegistry | None = None,
        model_router: ModelRouter | None = None,
        knowledge: VerifiedKnowledgeStore | None = None,
    ):
        self.memory = memory or DevelopmentMemory()
        self.tools = tools or AgentToolRegistry()
        self.specialists = specialists or SpecialistAgentRegistry(self.tools)
        self.model_router = model_router or ModelRouter()
        self.knowledge = knowledge or VerifiedKnowledgeStore()

    def plan(self, goal: str, project_slug: str | None = None) -> AgentPlan:
        goal = goal.strip()
        if not goal:
            raise ValueError("goal is required")
        run_id = uuid.uuid4().hex
        steps = [
            AgentStep("understand", "understand", "目的を理解", "依頼内容・制約・成功条件を整理する", None, ("coordinator",)),
            AgentStep("inspect", "inspect", "現状を確認", "既存コード・履歴・テスト・過去の改善点を確認する", "project.inspect", ("research", "architect")),
            AgentStep("plan", "plan", "実装計画", "変更範囲と検証方法を小さな単位へ分解する", None, ("coordinator", "architect")),
            AgentStep("generate", "generate", "実装", "既存機能を壊さない範囲でコードを生成・変更する", "code.generate", ("coding",)),
            AgentStep("validate-tests", "validate", "自動テスト", "承認済みTest Runnerで機能・構文・基本動作を検証する", "tests.run", ("test",)),
            AgentStep("validate-design", "validate", "Design確認", "Design AIでレスポンシブ・操作性・視認性を検証する", "design.review", ("design",)),
            AgentStep("validate-security", "validate", "Security確認", "秘密情報・危険コード・依存関係の問題を検証する", "security.scan", ("security",)),
            AgentStep("repair", "repair", "必要なら修正", "失敗原因だけを材料に最大2回まで安全に修正する", "code.repair", ("coding", "test")),
            AgentStep("package", "package", "成果物を準備", "対象OS/形式の成果物を生成できる場合だけ生成する", "package.build", ("build",)),
            AgentStep("review", "review", "公開前確認", "外部公開・署名・ストア提出などは人の承認を要求する", "release.publish", ("release",), True),
            AgentStep("report", "report", "根拠付き報告", "できたこと・できないこと・証拠・次の課題を報告する", None, ("coordinator",)),
        ]
        for step in steps:
            for specialist_name in step.specialists:
                self.specialists.get(specialist_name)
            if step.tool_name:
                tool = self.tools.get(step.tool_name)
                if tool.requires_human_approval != step.requires_human_approval and step.action == "review":
                    raise RuntimeError("agent plan approval contract mismatch")
        return AgentPlan(run_id, goal, project_slug, _now(), steps, 2)

    def context(self, goal: str, limit: int = 5) -> dict[str, Any]:
        lessons = self.memory.lessons_for(goal, limit=limit, verified_only=True)
        knowledge = self.knowledge.search(goal, verified_only=True, limit=limit)
        specialist_rows = []
        for specialist in self.specialists.list():
            route = self.model_router.route(specialist.model_task)
            specialist_rows.append({
                "name": specialist.name,
                "title": specialist.title,
                "model_task": specialist.model_task,
                "route": route.to_dict(),
                "allowed_tools": list(specialist.allowed_tools),
            })
        return {
            "goal": goal,
            "lessons": lessons,
            "verified_knowledge": [x.to_dict() for x in knowledge],
            "specialists": specialist_rows,
            "policy": {
                "arbitrary_shell": False,
                "max_repair_attempts": 2,
                "human_approval_for_external_actions": True,
                "evidence_required_for_completion": True,
                "untrusted_web_never_directly_verified": True,
                "registered_tools": [x.name for x in self.tools.list()],
            },
        }

    def completion_check(
        self,
        evidence: list[EvidenceRecord],
        *,
        require_package: bool = False,
        require_human_review: bool = False,
    ) -> dict[str, Any]:
        by_stage: dict[str, list[EvidenceRecord]] = {}
        for row in evidence:
            by_stage.setdefault(row.stage, []).append(row)

        blockers = [
            row.summary
            for row in evidence
            if row.status.lower() in {"blocked", "fail", "failed", "error"}
        ]
        required = ["plan", "validate", "report"]
        if require_package:
            required.append("package")
        if require_human_review:
            required.append("review")

        missing: list[str] = []
        for stage in required:
            rows = by_stage.get(stage, [])
            if not rows:
                missing.append(stage)
                continue
            if stage == "validate":
                if not any(x.status.lower() in {"pass", "verified", "success"} for x in rows):
                    missing.append(stage)
            elif stage == "report":
                if not any(x.status.lower() in {"verified", "success"} for x in rows):
                    missing.append(stage)
            elif stage == "review" and require_human_review:
                if not any(x.status.lower() in {"approved", "verified"} for x in rows):
                    missing.append(stage)

        complete = not blockers and not missing
        return {
            "complete": complete,
            "missing_evidence": missing,
            "blocking_evidence": blockers,
            "rule": "agent completion requires evidence; self-assertion alone is insufficient",
        }

    def learn_from_verified_outcome(
        self,
        *,
        goal: str,
        lesson: str,
        outcome: str,
        project_slug: str | None = None,
        verified: bool,
    ) -> dict[str, Any]:
        if not verified:
            return {"recorded": False, "reason": "unverified outcomes are not reusable lessons"}
        item = self.memory.record(
            category="agent_verified_outcome",
            input_text=goal,
            lesson=lesson,
            outcome=outcome,
            project_slug=project_slug,
            verified=True,
            evidence_source="agent-verified-outcome",
        )
        log_event(
            "agent.lesson_recorded",
            json.dumps(asdict(item), ensure_ascii=False),
            project_slug,
            "agent-orchestrator",
        )
        return {"recorded": True, "item": asdict(item)}
