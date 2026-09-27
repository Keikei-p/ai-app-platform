from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json
import uuid

from .agent_budget import AgentBudget, AgentBudgetTracker
from .agent_tool_executor import AgentToolExecutor
from .agent_tools import AgentToolRegistry
from .llm_chat import AIChatEngine
from .model_router import ModelRouter
from .redaction import redact_sensitive
from .specialist_agents import SpecialistAgentRegistry
from .specialist_runtime import SpecialistRuntime, SpecialistResult


DEFAULT_EXECUTION_COUNCIL = (
    "research",
    "architect",
    "coding",
    "test",
    "design",
    "security",
    "build",
    "coordinator",
)

SAFE_COUNCIL_EXECUTION_TOOLS = {
    "project.inspect",
    "knowledge.search",
    "tests.run",
    "design.review",
    "security.scan",
}


@dataclass(frozen=True)
class CouncilToolExecution:
    specialist: str
    tool_name: str
    status: str
    summary: str
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionCouncilTurn:
    order: int
    specialist: str
    result: SpecialistResult
    tool_executions: tuple[CouncilToolExecution, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "specialist": self.specialist,
            "result": self.result.to_dict(),
            "tool_executions": [x.to_dict() for x in self.tool_executions],
        }


@dataclass(frozen=True)
class ExecutionCouncilReport:
    run_id: str
    goal: str
    project_slug: str
    status: str
    execution_mode: str
    turns: tuple[ExecutionCouncilTurn, ...]
    executed_tools: tuple[str, ...]
    delegated_tools: tuple[str, ...]
    approval_required_tools: tuple[str, ...]
    tool_executions: tuple[CouncilToolExecution, ...]
    budget: dict[str, Any]
    summary: str
    evidence_state: str
    validation: dict[str, Any]
    external_actions_blocked: bool = True
    history_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "goal": self.goal,
            "project_slug": self.project_slug,
            "status": self.status,
            "execution_mode": self.execution_mode,
            "turns": [x.to_dict() for x in self.turns],
            "executed_tools": list(self.executed_tools),
            "delegated_tools": list(self.delegated_tools),
            "approval_required_tools": list(self.approval_required_tools),
            "tool_executions": [x.to_dict() for x in self.tool_executions],
            "budget": self.budget,
            "summary": self.summary,
            "evidence_state": self.evidence_state,
            "validation": self.validation,
            "external_actions_blocked": self.external_actions_blocked,
            "history_path": self.history_path,
        }


class SpecialistExecutionCouncil:
    """Specialist collaboration with a tiny reviewed local-tool execution surface.

    The model never supplies command lines or arbitrary tool arguments. Tool names
    are first constrained by each specialist's role contract, then by the registry,
    then by this council's immutable safe execution set, and finally by the reviewed
    AgentToolExecutor binding. Code generation, packaging, export, publishing, store
    submission, and any approval-gated operation remain delegated.
    """

    MAX_TOOL_EXECUTIONS = len(SAFE_COUNCIL_EXECUTION_TOOLS)

    def __init__(
        self,
        *,
        engine: AIChatEngine | None = None,
        tools: AgentToolRegistry | None = None,
        specialists: SpecialistAgentRegistry | None = None,
        router: ModelRouter | None = None,
        executor: AgentToolExecutor,
    ):
        self.engine = engine or AIChatEngine()
        self.tools = tools or executor.registry
        self.specialists = specialists or SpecialistAgentRegistry(self.tools)
        self.router = router or ModelRouter(self.engine)
        self.executor = executor

    def run(
        self,
        goal: str,
        project_slug: str,
        *,
        context: dict[str, Any] | None = None,
        roles: tuple[str, ...] | None = None,
    ) -> ExecutionCouncilReport:
        clean_goal = goal.strip()
        slug = project_slug.strip()
        if not clean_goal:
            raise ValueError("goal is required")
        if not slug:
            raise ValueError("project_slug is required")
        run_id = "council-" + uuid.uuid4().hex

        selected = tuple(roles or DEFAULT_EXECUTION_COUNCIL)
        if not selected or len(selected) > len(DEFAULT_EXECUTION_COUNCIL):
            raise ValueError("invalid specialist execution council size")
        if len(set(selected)) != len(selected):
            raise ValueError("specialist execution council roles must be unique")
        if any(name not in set(DEFAULT_EXECUTION_COUNCIL) for name in selected):
            raise ValueError("unsupported specialist execution council role")

        tracker = AgentBudgetTracker(
            AgentBudget(
                max_model_calls=len(DEFAULT_EXECUTION_COUNCIL),
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
            "goal": clean_goal,
            "project_slug": slug,
            "base_context": dict(context or {}),
            "prior_specialists": [],
            "verified_tool_evidence": [],
            "council_rules": {
                "tool_execution": "reviewed_local_validation_only",
                "arbitrary_shell": False,
                "code_generation": False,
                "package_build": False,
                "external_actions": False,
                "approval_bypass": False,
            },
        }
        turns: list[ExecutionCouncilTurn] = []
        executions: list[CouncilToolExecution] = []
        executed: list[str] = []
        delegated: list[str] = []
        approval_required: list[str] = []
        executed_once: dict[str, CouncilToolExecution] = {}
        blocked = False

        for order, name in enumerate(selected, start=1):
            specialist = self.specialists.get(name)
            try:
                result = runtime.consult(
                    name,
                    self._task_for(name, clean_goal),
                    shared,
                )
            except Exception as exc:
                summary = f"specialist execution council stopped safely: {type(exc).__name__}: {exc}"
                return self._report(
                    run_id,
                    clean_goal,
                    slug,
                    "blocked",
                    turns,
                    executed,
                    delegated,
                    approval_required,
                    executions,
                    tracker,
                    summary,
                )

            if result.status == "not_connected":
                turns.append(ExecutionCouncilTurn(order, name, result, ()))
                return self._report(
                    run_id,
                    clean_goal,
                    slug,
                    "not_connected",
                    turns,
                    executed,
                    delegated,
                    approval_required,
                    executions,
                    tracker,
                    "External AI is not connected; no execution council tools were run.",
                )

            turn_execs: list[CouncilToolExecution] = []
            role_allowed = set(specialist.allowed_tools)

            for tool_name in result.requested_tools:
                if tool_name not in role_allowed:
                    raise RuntimeError("specialist tool allowlist invariant failed")

                definition = self.tools.get(tool_name)
                if definition.requires_human_approval:
                    approval_required.append(tool_name)
                    row = CouncilToolExecution(
                        name,
                        tool_name,
                        "approval_required",
                        "Tool was not executed because explicit human approval is required.",
                        None,
                    )
                    executions.append(row)
                    turn_execs.append(row)
                    continue

                if tool_name not in SAFE_COUNCIL_EXECUTION_TOOLS:
                    delegated.append(tool_name)
                    row = CouncilToolExecution(
                        name,
                        tool_name,
                        "delegated",
                        "Tool is outside the execution council's reviewed read/validation surface.",
                        None,
                    )
                    executions.append(row)
                    turn_execs.append(row)
                    continue

                if tool_name not in set(self.executor.executable_tools()):
                    delegated.append(tool_name)
                    row = CouncilToolExecution(
                        name,
                        tool_name,
                        "delegated",
                        "Tool has no reviewed executor binding.",
                        None,
                    )
                    executions.append(row)
                    turn_execs.append(row)
                    continue

                if tool_name in executed_once:
                    previous = executed_once[tool_name]
                    row = CouncilToolExecution(
                        name,
                        tool_name,
                        "reused",
                        "A prior specialist already produced current evidence for this tool.",
                        previous.result,
                    )
                    executions.append(row)
                    turn_execs.append(row)
                    continue

                if len(executed_once) >= self.MAX_TOOL_EXECUTIONS:
                    blocked = True
                    row = CouncilToolExecution(
                        name,
                        tool_name,
                        "budget_blocked",
                        "Execution council tool budget was exhausted.",
                        None,
                    )
                    executions.append(row)
                    turn_execs.append(row)
                    break

                try:
                    execution = self.executor.execute(
                        tool_name,
                        self._tool_args(tool_name, clean_goal, slug),
                        approved=False,
                        run_id=run_id,
                    )
                except Exception as exc:
                    blocked = True
                    row = CouncilToolExecution(
                        name,
                        tool_name,
                        "error",
                        f"{type(exc).__name__}: {redact_sensitive(str(exc))[:1000]}",
                        None,
                    )
                    executions.append(row)
                    turn_execs.append(row)
                    break

                bounded_result = self._bounded_result(execution.result)
                row = CouncilToolExecution(
                    name,
                    tool_name,
                    "executed",
                    "Reviewed local tool executed and evidence was returned to later specialists.",
                    bounded_result,
                )
                executed_once[tool_name] = row
                executed.append(tool_name)
                executions.append(row)
                turn_execs.append(row)
                shared["verified_tool_evidence"].append({
                    "tool_name": tool_name,
                    "result": bounded_result,
                })

            turns.append(ExecutionCouncilTurn(order, name, result, tuple(turn_execs)))
            shared["prior_specialists"].append({
                "specialist": name,
                "summary": result.summary,
                "findings": list(result.findings),
                "recommendations": list(result.recommendations),
                "uncertainties": list(result.uncertainties),
                "requested_tools": list(result.requested_tools),
                "tool_status": [
                    {"tool_name": row.tool_name, "status": row.status}
                    for row in turn_execs
                ],
            })
            if blocked:
                break

        status = "blocked" if blocked else "completed"
        coordinator = next((x.result for x in reversed(turns) if x.specialist == "coordinator"), None)
        summary = (
            coordinator.summary
            if coordinator is not None and coordinator.summary.strip()
            else f"{len(turns)} specialists completed with {len(executed_once)} reviewed tool executions."
        )
        return self._report(
            run_id,
            clean_goal,
            slug,
            status,
            turns,
            executed,
            delegated,
            approval_required,
            executions,
            tracker,
            summary,
        )

    def _report(
        self,
        run_id: str,
        goal: str,
        project_slug: str,
        status: str,
        turns: list[ExecutionCouncilTurn],
        executed: list[str],
        delegated: list[str],
        approval_required: list[str],
        executions: list[CouncilToolExecution],
        tracker: AgentBudgetTracker,
        summary: str,
    ) -> ExecutionCouncilReport:
        budget = tracker.snapshot()
        budget["used"]["tool_executions"] = len({
            x.tool_name for x in executions if x.status == "executed"
        })
        budget["budget"]["max_tool_executions"] = self.MAX_TOOL_EXECUTIONS
        validation = self._validation_state(executions)
        return ExecutionCouncilReport(
            run_id=run_id,
            goal=goal,
            project_slug=project_slug,
            status=status,
            execution_mode="reviewed_local_validation_only",
            turns=tuple(turns),
            executed_tools=tuple(dict.fromkeys(executed)),
            delegated_tools=tuple(dict.fromkeys(delegated)),
            approval_required_tools=tuple(dict.fromkeys(approval_required)),
            tool_executions=tuple(executions),
            budget=budget,
            summary=summary,
            evidence_state=str(validation["state"]),
            validation=validation,
            external_actions_blocked=True,
        )

    @staticmethod
    def save(project_dir: Path, report: ExecutionCouncilReport) -> Path:
        root = Path(project_dir)
        target = root / ".aiapp" / "agent" / "councils" / f"{report.run_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": report.run_id,
            "goal": redact_sensitive(report.goal)[:3000],
            "project_slug": report.project_slug,
            "status": report.status,
            "execution_mode": report.execution_mode,
            "executed_tools": list(report.executed_tools),
            "delegated_tools": list(report.delegated_tools),
            "approval_required_tools": list(report.approval_required_tools),
            "budget": report.budget,
            "summary": redact_sensitive(report.summary)[:3000],
            "evidence_state": report.evidence_state,
            "validation": report.validation,
            "external_actions_blocked": report.external_actions_blocked,
            "turns": [
                {
                    "order": turn.order,
                    "specialist": turn.specialist,
                    "status": turn.result.status,
                    "summary": redact_sensitive(turn.result.summary)[:2000],
                    "requested_tools": list(turn.result.requested_tools),
                    "tool_executions": [
                        {
                            "tool_name": row.tool_name,
                            "status": row.status,
                            "summary": redact_sensitive(row.summary)[:1000],
                        }
                        for row in turn.tool_executions
                    ],
                }
                for turn in report.turns
            ],
        }
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
        return target

    @staticmethod
    def _validation_state(executions: list[CouncilToolExecution]) -> dict[str, Any]:
        latest: dict[str, CouncilToolExecution] = {}
        for row in executions:
            if row.status in {"executed", "reused"} and row.result is not None:
                latest[row.tool_name] = row

        values: dict[str, bool | None] = {
            "tests.run": None,
            "design.review": None,
            "security.scan": None,
        }
        tests = latest.get("tests.run")
        if tests is not None and isinstance(tests.result, dict):
            values["tests.run"] = bool(tests.result.get("passed"))
        design = latest.get("design.review")
        if design is not None and isinstance(design.result, dict):
            values["design.review"] = bool((design.result.get("review") or {}).get("passed"))
        security = latest.get("security.scan")
        if security is not None and isinstance(security.result, dict):
            values["security.scan"] = bool((security.result.get("security") or {}).get("passed"))

        present = [x for x in values.values() if x is not None]
        if any(x is False for x in present):
            state = "failed"
        elif all(values[name] is True for name in values):
            state = "verified"
        else:
            state = "partial"
        return {
            "state": state,
            "checks": values,
            "rule": "Only actual reviewed tests/design/security tool results determine verification state.",
        }

    @staticmethod
    def _tool_args(tool_name: str, goal: str, project_slug: str) -> dict[str, Any]:
        if tool_name == "project.inspect":
            return {"project_slug": project_slug}
        if tool_name == "knowledge.search":
            return {"query": goal, "limit": 5}
        if tool_name in {"tests.run", "design.review", "security.scan"}:
            return {"project_slug": project_slug}
        raise PermissionError("execution council has no reviewed argument builder for tool")

    @staticmethod
    def _bounded_result(result: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(result, ensure_ascii=False, default=str)
        if len(raw) > 8_000:
            return {"truncated_verified_result": redact_sensitive(raw[:8_000])}
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}

    @staticmethod
    def _task_for(name: str, goal: str) -> str:
        tasks = {
            "research": f"Identify verified facts, unknowns, and evidence needed for: {goal}",
            "architect": f"Use available evidence to propose the smallest safe architecture for: {goal}",
            "coding": f"Identify bounded source changes needed for: {goal}; do not execute code generation here",
            "test": f"Use current evidence to determine what tests should verify for: {goal}",
            "design": f"Use current evidence to assess UX and responsive quality for: {goal}",
            "security": f"Use current evidence to assess security and release blockers for: {goal}",
            "build": f"Use current evidence to identify package requirements for: {goal}; do not build here",
            "coordinator": f"Synthesize specialist conclusions and verified tool evidence for: {goal}",
        }
        return tasks[name]
