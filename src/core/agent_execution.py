from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import uuid

from .agent_budget import AgentBudget, AgentBudgetTracker
from .agent_tool_executor import AgentToolExecutor
from .agent_tools import AgentToolRegistry
from .specialist_agents import SpecialistAgentRegistry
from .specialist_council import CouncilReport


@dataclass(frozen=True)
class AgentToolRun:
    specialist: str
    tool_name: str
    status: str
    detail: str
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentExecutionReport:
    run_id: str
    goal: str
    project_slug: str | None
    status: str
    executed: tuple[AgentToolRun, ...]
    skipped: tuple[AgentToolRun, ...]
    budget: dict[str, Any]
    external_actions_blocked: bool

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["executed"] = [x.to_dict() for x in self.executed]
        data["skipped"] = [x.to_dict() for x in self.skipped]
        return data


class AgentExecutionLoop:
    """Execute a safe subset of specialist-requested tools.

    Specialists request tool names only. This loop derives reviewed arguments
    from trusted runtime context, re-validates the role allowlist, requires an
    executor binding, enforces a tool-call budget, and never executes approval-
    gated or external release tools.
    """

    def __init__(
        self,
        *,
        executor: AgentToolExecutor,
        tools: AgentToolRegistry | None = None,
        specialists: SpecialistAgentRegistry | None = None,
        budget: AgentBudget | None = None,
    ):
        self.executor = executor
        self.tools = tools or AgentToolRegistry()
        self.specialists = specialists or SpecialistAgentRegistry(self.tools)
        self.budget = budget or AgentBudget()

    def run(
        self,
        council: CouncilReport,
        *,
        project_slug: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgentExecutionReport:
        if council.status != "ok":
            return AgentExecutionReport(
                run_id="agent-exec-" + uuid.uuid4().hex,
                goal=council.goal,
                project_slug=project_slug,
                status="not_executed",
                executed=(),
                skipped=(),
                budget=AgentBudgetTracker(self.budget).snapshot(),
                external_actions_blocked=True,
            )

        run_id = "agent-exec-" + uuid.uuid4().hex
        tracker = AgentBudgetTracker(self.budget)
        executed: list[AgentToolRun] = []
        skipped: list[AgentToolRun] = []
        executable = set(self.executor.executable_tools())
        seen: set[tuple[str, str]] = set()
        safe_context = dict(context or {})

        for turn in council.turns:
            specialist = self.specialists.get(turn.specialist)
            allowed = set(specialist.allowed_tools)
            for tool_name in turn.result.requested_tools:
                key = (turn.specialist, tool_name)
                if key in seen:
                    continue
                seen.add(key)

                try:
                    definition = self.tools.get(tool_name)
                except KeyError:
                    skipped.append(AgentToolRun(
                        turn.specialist, tool_name, "blocked", "tool is not registered"
                    ))
                    continue

                if tool_name not in allowed:
                    skipped.append(AgentToolRun(
                        turn.specialist, tool_name, "blocked", "tool is outside specialist allowlist"
                    ))
                    continue

                if definition.requires_human_approval:
                    skipped.append(AgentToolRun(
                        turn.specialist, tool_name, "approval_required",
                        "approval-gated tools are never auto-executed by the agent loop",
                    ))
                    continue

                if tool_name not in executable:
                    skipped.append(AgentToolRun(
                        turn.specialist, tool_name, "not_bound",
                        "tool has no reviewed executor binding",
                    ))
                    continue

                args = self._args_for(
                    tool_name,
                    goal=council.goal,
                    project_slug=project_slug,
                    context=safe_context,
                    tracker=tracker,
                )
                if args is None:
                    skipped.append(AgentToolRun(
                        turn.specialist, tool_name, "missing_context",
                        "required trusted context is unavailable",
                    ))
                    continue

                try:
                    tracker.reserve_tool_call()
                    result = self.executor.execute(
                        tool_name,
                        args,
                        approved=False,
                        run_id=run_id,
                    )
                except Exception as exc:
                    skipped.append(AgentToolRun(
                        turn.specialist,
                        tool_name,
                        "blocked",
                        f"{type(exc).__name__}: {exc}",
                    ))
                    continue

                executed.append(AgentToolRun(
                    turn.specialist,
                    tool_name,
                    "executed",
                    "reviewed executor binding completed",
                    result.to_dict(),
                ))

        status = "completed" if executed else "no_safe_tools"
        return AgentExecutionReport(
            run_id=run_id,
            goal=council.goal,
            project_slug=project_slug,
            status=status,
            executed=tuple(executed),
            skipped=tuple(skipped),
            budget=tracker.snapshot(),
            external_actions_blocked=True,
        )

    @staticmethod
    def _args_for(
        tool_name: str,
        *,
        goal: str,
        project_slug: str | None,
        context: dict[str, Any],
        tracker: AgentBudgetTracker,
    ) -> dict[str, Any] | None:
        if tool_name in {
            "project.inspect", "vault.snapshot", "tests.run",
            "design.review", "security.scan",
        }:
            if not project_slug:
                return None
            if tool_name == "vault.snapshot":
                return {"project_slug": project_slug, "label": "agent-reviewed-checkpoint"}
            return {"project_slug": project_slug}

        if tool_name == "knowledge.search":
            return {"query": goal, "limit": 5}

        if tool_name == "research.fetch":
            urls = context.get("research_urls")
            if not isinstance(urls, list):
                return None
            clean = [str(x).strip() for x in urls if str(x).strip()]
            if not clean:
                return None
            tracker.reserve_research_sources(1)
            return {"url": clean[0]}

        if tool_name == "evolution.compare":
            baseline = context.get("baseline")
            candidate = context.get("candidate")
            changed_paths = context.get("changed_paths")
            evidence_refs = context.get("evidence_refs")
            if not isinstance(baseline, dict) or not isinstance(candidate, dict):
                return None
            if not isinstance(changed_paths, list) or not isinstance(evidence_refs, list):
                return None
            return {
                "baseline": baseline,
                "candidate": candidate,
                "changed_paths": [str(x) for x in changed_paths],
                "evidence_refs": [str(x) for x in evidence_refs],
                "requested_actions": [],
            }

        return None
