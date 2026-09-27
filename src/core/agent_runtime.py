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

    def __init__(self, memory: DevelopmentMemory | None = None):
        self.memory = memory or DevelopmentMemory()

    def plan(self, goal: str, project_slug: str | None = None) -> AgentPlan:
        goal = goal.strip()
        if not goal:
            raise ValueError("goal is required")
        run_id = uuid.uuid4().hex
        steps = [
            AgentStep("understand", "understand", "目的を理解", "依頼内容・制約・成功条件を整理する"),
            AgentStep("inspect", "inspect", "現状を確認", "既存コード・履歴・テスト・過去の改善点を確認する"),
            AgentStep("plan", "plan", "実装計画", "変更範囲と検証方法を小さな単位へ分解する"),
            AgentStep("generate", "generate", "実装", "既存機能を壊さない範囲でコードを生成・変更する"),
            AgentStep("validate", "validate", "検証", "テスト・Design AI・Security Gateで根拠を集める"),
            AgentStep("repair", "repair", "必要なら修正", "失敗原因だけを材料に最大2回まで安全に修正する"),
            AgentStep("package", "package", "成果物を準備", "対象OS/形式の成果物を生成できる場合だけ生成する"),
            AgentStep("review", "review", "公開前確認", "外部公開・署名・ストア提出などは人の承認を要求する", True),
            AgentStep("report", "report", "根拠付き報告", "できたこと・できないこと・証拠・次の課題を報告する"),
        ]
        return AgentPlan(run_id, goal, project_slug, _now(), steps, 2)

    def context(self, goal: str, limit: int = 5) -> dict[str, Any]:
        lessons = self.memory.lessons_for(goal, limit=limit, verified_only=True)
        return {
            "goal": goal,
            "lessons": lessons,
            "policy": {
                "arbitrary_shell": False,
                "max_repair_attempts": 2,
                "human_approval_for_external_actions": True,
                "evidence_required_for_completion": True,
            },
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
