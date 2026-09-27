from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .agent_budget import AgentBudget, AgentBudgetTracker
from .agent_tools import AgentToolRegistry
from .llm_chat import AIChatEngine
from .model_router import ModelRouter
from .specialist_agents import SpecialistAgentRegistry
from .specialist_runtime import SpecialistRuntime, SpecialistResult


DEFAULT_COUNCIL = (
    "research",
    "architect",
    "coding",
    "test",
    "design",
    "security",
    "build",
    "coordinator",
)


@dataclass(frozen=True)
class CouncilTurn:
    order: int
    specialist: str
    result: SpecialistResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "specialist": self.specialist,
            "result": self.result.to_dict(),
        }


@dataclass(frozen=True)
class CouncilReport:
    goal: str
    status: str
    advisory_only: bool
    turns: tuple[CouncilTurn, ...]
    requested_tools: tuple[str, ...]
    approval_required_tools: tuple[str, ...]
    budget: dict[str, Any]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "status": self.status,
            "advisory_only": self.advisory_only,
            "turns": [x.to_dict() for x in self.turns],
            "requested_tools": list(self.requested_tools),
            "approval_required_tools": list(self.approval_required_tools),
            "budget": self.budget,
            "summary": self.summary,
        }


class SpecialistCouncil:
    """Bounded sequential consultation across Aivy's specialist agents.

    The council only produces analysis and tool requests. It never executes tools,
    edits files, publishes, installs dependencies, or bypasses approval gates.
    Each specialist receives a compact record of prior specialist conclusions so
    the council behaves as a connected team rather than unrelated model calls.
    """

    def __init__(
        self,
        *,
        engine: AIChatEngine | None = None,
        tools: AgentToolRegistry | None = None,
        specialists: SpecialistAgentRegistry | None = None,
        router: ModelRouter | None = None,
    ):
        self.engine = engine or AIChatEngine()
        self.tools = tools or AgentToolRegistry()
        self.specialists = specialists or SpecialistAgentRegistry(self.tools)
        self.router = router or ModelRouter(self.engine)

    def run(
        self,
        goal: str,
        *,
        context: dict[str, Any] | None = None,
        roles: tuple[str, ...] | None = None,
    ) -> CouncilReport:
        goal = goal.strip()
        if not goal:
            raise ValueError("goal is required")

        selected = tuple(roles or DEFAULT_COUNCIL)
        if not selected or len(selected) > len(DEFAULT_COUNCIL):
            raise ValueError("invalid specialist council size")
        if len(set(selected)) != len(selected):
            raise ValueError("specialist council roles must be unique")
        allowed_roles = set(DEFAULT_COUNCIL)
        if any(name not in allowed_roles for name in selected):
            raise ValueError("unsupported specialist council role")

        tracker = AgentBudgetTracker(
            AgentBudget(
                max_model_calls=len(DEFAULT_COUNCIL),
                max_research_sources=8,
                max_repair_attempts=2,
                max_specialist_output_chars=12_000,
            )
        )
        runtime = SpecialistRuntime(
            engine=self.engine,
            registry=self.specialists,
            router=self.router,
            budget=tracker,
        )

        shared: dict[str, Any] = {
            "goal": goal,
            "base_context": dict(context or {}),
            "prior_specialists": [],
            "council_rules": {
                "advisory_only": True,
                "tool_execution": False,
                "evidence_required_before_completion": True,
            },
        }
        turns: list[CouncilTurn] = []
        requested: list[str] = []

        for order, name in enumerate(selected, start=1):
            task = self._task_for(name, goal)
            try:
                result = runtime.consult(name, task, shared)
            except Exception as exc:
                return CouncilReport(
                    goal=goal,
                    status="blocked",
                    advisory_only=True,
                    turns=tuple(turns),
                    requested_tools=tuple(dict.fromkeys(requested)),
                    approval_required_tools=self._approval_tools(requested),
                    budget=tracker.snapshot(),
                    summary=f"specialist council stopped safely: {type(exc).__name__}: {exc}",
                )

            turn = CouncilTurn(order, name, result)
            turns.append(turn)
            requested.extend(result.requested_tools)

            shared["prior_specialists"].append({
                "specialist": name,
                "summary": result.summary,
                "findings": list(result.findings),
                "recommendations": list(result.recommendations),
                "uncertainties": list(result.uncertainties),
                "requested_tools": list(result.requested_tools),
            })

            if result.status == "not_connected":
                return CouncilReport(
                    goal=goal,
                    status="not_connected",
                    advisory_only=True,
                    turns=tuple(turns),
                    requested_tools=(),
                    approval_required_tools=(),
                    budget=tracker.snapshot(),
                    summary="External AI is not connected; the specialist council did not run.",
                )

        unique_tools = tuple(dict.fromkeys(requested))
        coordinator = next((x.result for x in reversed(turns) if x.specialist == "coordinator"), None)
        summary = (
            coordinator.summary
            if coordinator is not None and coordinator.summary.strip()
            else f"{len(turns)} specialists completed bounded advisory consultation."
        )
        return CouncilReport(
            goal=goal,
            status="ok",
            advisory_only=True,
            turns=tuple(turns),
            requested_tools=unique_tools,
            approval_required_tools=self._approval_tools(unique_tools),
            budget=tracker.snapshot(),
            summary=summary,
        )

    def _approval_tools(self, names: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            name
            for name in dict.fromkeys(names)
            if self.tools.requires_approval(name)
        )

    @staticmethod
    def _task_for(name: str, goal: str) -> str:
        tasks = {
            "research": f"Identify current technical facts, unknowns, and research needs for: {goal}",
            "architect": f"Propose a minimal maintainable architecture and boundaries for: {goal}",
            "coding": f"Identify the bounded source changes needed to implement: {goal}",
            "test": f"Define deterministic acceptance and regression tests for: {goal}",
            "design": f"Review the required UX, responsive behavior, accessibility, and visual quality for: {goal}",
            "security": f"Identify security, secret-handling, dependency, and release risks for: {goal}",
            "build": f"Identify build/package requirements and artifact evidence needed for: {goal}",
            "coordinator": f"Synthesize the specialist conclusions, unresolved uncertainty, and safe next actions for: {goal}",
        }
        return tasks[name]
