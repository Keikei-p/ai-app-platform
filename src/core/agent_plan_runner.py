from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .agent_runtime import AgentPlan, AgentStep, EvidenceLedger
from .agent_tool_executor import AgentToolExecutor
from .agent_tools import AgentToolRegistry


@dataclass(frozen=True)
class AgentStepExecution:
    step_id: str
    action: str
    tool_name: str | None
    status: str
    summary: str
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentRunReport:
    run_id: str
    goal: str
    project_slug: str | None
    status: str
    executed_tools: tuple[str, ...]
    delegated_tools: tuple[str, ...]
    approval_required: tuple[str, ...]
    steps: tuple[AgentStepExecution, ...]
    arbitrary_shell: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["executed_tools"] = list(self.executed_tools)
        data["delegated_tools"] = list(self.delegated_tools)
        data["approval_required"] = list(self.approval_required)
        data["steps"] = [x.to_dict() for x in self.steps]
        return data


class AgentPlanRunner:
    """Run only reviewed Agent Tool Executor bindings from an AgentPlan.

    The runner cannot create arbitrary commands, cannot call unbound tools, and
    never treats a registered tool as executable merely because it exists in the
    registry. Unbound implementation/package tools stay delegated to existing
    platform pipelines. Approval-gated tools stop at human review.
    """

    MAX_STEPS = 20

    def __init__(
        self,
        executor: AgentToolExecutor,
        *,
        registry: AgentToolRegistry | None = None,
    ):
        self.executor = executor
        self.registry = registry or executor.registry

    def run(
        self,
        plan: AgentPlan,
        *,
        project_dir: Path | None = None,
        approved_tools: set[str] | None = None,
        tool_args: dict[str, dict[str, Any]] | None = None,
    ) -> AgentRunReport:
        if len(plan.steps) > self.MAX_STEPS:
            raise ValueError("agent plan exceeds safe step budget")
        approved = set(approved_tools or ())
        args_by_tool = dict(tool_args or {})
        executable = set(self.executor.executable_tools())
        ledger = EvidenceLedger(project_dir) if project_dir is not None else EvidenceLedger()

        rows: list[AgentStepExecution] = []
        executed: list[str] = []
        delegated: list[str] = []
        waiting: list[str] = []
        blocked = False

        for step in plan.steps:
            if step.tool_name is None:
                rows.append(AgentStepExecution(
                    step.step_id,
                    step.action,
                    None,
                    "planned",
                    step.purpose,
                    None,
                ))
                continue

            definition = self.registry.get(step.tool_name)
            if definition.requires_human_approval and step.tool_name not in approved:
                summary = f"human approval required before {step.tool_name}"
                ledger.record(
                    run_id=plan.run_id,
                    stage=step.action,
                    status="approval_required",
                    summary=summary,
                    source="agent-plan-runner",
                )
                waiting.append(step.tool_name)
                rows.append(AgentStepExecution(
                    step.step_id,
                    step.action,
                    step.tool_name,
                    "approval_required",
                    summary,
                    None,
                ))
                break

            if step.tool_name not in executable:
                summary = f"{step.tool_name} is delegated to the reviewed platform pipeline"
                ledger.record(
                    run_id=plan.run_id,
                    stage=step.action,
                    status="delegated",
                    summary=summary,
                    source="agent-plan-runner",
                )
                delegated.append(step.tool_name)
                rows.append(AgentStepExecution(
                    step.step_id,
                    step.action,
                    step.tool_name,
                    "delegated",
                    summary,
                    None,
                ))
                continue

            payload = dict(args_by_tool.get(step.tool_name) or {})
            if plan.project_slug and step.tool_name in {
                "project.inspect",
                "vault.snapshot",
                "tests.run",
                "design.review",
                "security.scan",
            }:
                payload.setdefault("project_slug", plan.project_slug)
            if step.tool_name == "knowledge.search":
                payload.setdefault("query", plan.goal)

            try:
                execution = self.executor.execute(
                    step.tool_name,
                    payload,
                    approved=step.tool_name in approved,
                    run_id=plan.run_id,
                )
            except Exception as exc:
                summary = f"{type(exc).__name__}: {exc}"
                ledger.record(
                    run_id=plan.run_id,
                    stage=step.action,
                    status="error",
                    summary=summary,
                    source="agent-plan-runner",
                )
                rows.append(AgentStepExecution(
                    step.step_id,
                    step.action,
                    step.tool_name,
                    "error",
                    summary,
                    None,
                ))
                blocked = True
                break

            result = execution.result
            passed = self._result_passed(step.tool_name, result)
            status = "executed" if passed is not False else "failed"
            summary = (
                f"{step.tool_name} executed with reviewed binding"
                if passed is not False
                else f"{step.tool_name} reported a validation failure"
            )
            rows.append(AgentStepExecution(
                step.step_id,
                step.action,
                step.tool_name,
                status,
                summary,
                result,
            ))
            executed.append(step.tool_name)
            if passed is False:
                blocked = True
                ledger.record(
                    run_id=plan.run_id,
                    stage=step.action,
                    status="failed",
                    summary=summary,
                    source="agent-plan-runner",
                )
                break

        if blocked:
            overall = "blocked"
        elif waiting:
            overall = "approval_required"
        elif delegated:
            overall = "delegated_actions_pending"
        else:
            overall = "completed"

        return AgentRunReport(
            run_id=plan.run_id,
            goal=plan.goal,
            project_slug=plan.project_slug,
            status=overall,
            executed_tools=tuple(executed),
            delegated_tools=tuple(dict.fromkeys(delegated)),
            approval_required=tuple(dict.fromkeys(waiting)),
            steps=tuple(rows),
            arbitrary_shell=False,
        )

    @staticmethod
    def _result_passed(tool_name: str, result: dict[str, Any]) -> bool | None:
        if tool_name == "tests.run":
            return bool(result.get("passed"))
        if tool_name == "design.review":
            review = result.get("review") or {}
            return bool(review.get("passed"))
        if tool_name == "security.scan":
            report = result.get("security") or {}
            return bool(report.get("passed"))
        return None
