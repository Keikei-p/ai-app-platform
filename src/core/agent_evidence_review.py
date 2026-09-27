from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import json

from .agent_budget import AgentBudget, AgentBudgetTracker
from .agent_execution import AgentExecutionReport
from .llm_chat import AIChatEngine
from .model_router import ModelRouter
from .specialist_agents import SpecialistAgentRegistry
from .specialist_council import CouncilReport
from .specialist_runtime import SpecialistRuntime


@dataclass(frozen=True)
class EvidenceReviewReport:
    status: str
    evidence_state: str
    summary: str
    findings: tuple[str, ...]
    uncertainties: tuple[str, ...]
    requested_tools: tuple[str, ...]
    deterministic_checks: dict[str, Any]
    advisory_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["findings"] = list(self.findings)
        data["uncertainties"] = list(self.uncertainties)
        data["requested_tools"] = list(self.requested_tools)
        return data


class AgentEvidenceReviewer:
    """Feed actual reviewed-tool evidence back to the coordinator.

    The model can summarize evidence but cannot turn missing/failed evidence into
    a pass. Deterministic validation state is computed before the model call.
    """

    VALIDATION_TOOLS = ("tests.run", "design.review", "security.scan")

    def __init__(
        self,
        *,
        engine: AIChatEngine | None = None,
        specialists: SpecialistAgentRegistry | None = None,
        router: ModelRouter | None = None,
    ):
        self.engine = engine or AIChatEngine()
        self.specialists = specialists or SpecialistAgentRegistry()
        self.router = router or ModelRouter(self.engine)

    def review(
        self,
        goal: str,
        council: CouncilReport,
        execution: AgentExecutionReport,
    ) -> EvidenceReviewReport:
        checks = self._deterministic_checks(execution)
        evidence_state = checks["state"]

        tracker = AgentBudgetTracker(AgentBudget(max_model_calls=1))
        runtime = SpecialistRuntime(
            engine=self.engine,
            registry=self.specialists,
            router=self.router,
            budget=tracker,
        )

        context = {
            "goal": goal,
            "council_summary": council.summary,
            "actual_tool_evidence": {
                "executed": [self._compact_tool(x.to_dict()) for x in execution.executed],
                "skipped": [self._compact_tool(x.to_dict()) for x in execution.skipped],
            },
            "deterministic_checks": checks,
            "rules": {
                "failed_evidence_cannot_be_overridden": True,
                "missing_evidence_cannot_be_called_verified": True,
                "no_tool_execution_in_this_review": True,
            },
        }
        try:
            result = runtime.consult(
                "coordinator",
                (
                    "Review the actual tool evidence after the specialist council. "
                    "Summarize what is proven, what failed, and what remains unknown. "
                    "Never call the work complete when deterministic_checks state is not verified."
                ),
                context,
            )
        except Exception as exc:
            return EvidenceReviewReport(
                status="blocked",
                evidence_state=evidence_state,
                summary=f"evidence review stopped safely: {type(exc).__name__}: {exc}",
                findings=(),
                uncertainties=(),
                requested_tools=(),
                deterministic_checks=checks,
            )

        if result.status == "not_connected":
            return EvidenceReviewReport(
                status="not_connected",
                evidence_state=evidence_state,
                summary="External AI is not connected; deterministic evidence state is still available.",
                findings=(),
                uncertainties=("Coordinator model review was not performed.",),
                requested_tools=(),
                deterministic_checks=checks,
            )

        return EvidenceReviewReport(
            status="ok",
            evidence_state=evidence_state,
            summary=result.summary,
            findings=result.findings,
            uncertainties=result.uncertainties,
            requested_tools=result.requested_tools,
            deterministic_checks=checks,
        )

    @classmethod
    def _deterministic_checks(cls, execution: AgentExecutionReport) -> dict[str, Any]:
        by_tool = {x.tool_name: x for x in execution.executed}
        results: dict[str, bool | None] = {}
        for name in cls.VALIDATION_TOOLS:
            row = by_tool.get(name)
            if row is None or not isinstance(row.result, dict):
                results[name] = None
                continue
            payload = row.result.get("result") if isinstance(row.result.get("result"), dict) else {}
            if name == "tests.run":
                results[name] = bool(payload.get("passed"))
            elif name == "design.review":
                results[name] = bool((payload.get("review") or {}).get("passed"))
            elif name == "security.scan":
                results[name] = bool((payload.get("security") or {}).get("passed"))

        present = [x for x in results.values() if x is not None]
        if any(x is False for x in present):
            state = "failed"
        elif all(results[name] is True for name in cls.VALIDATION_TOOLS):
            state = "verified"
        else:
            state = "partial"

        return {
            "state": state,
            "validation": results,
            "rule": "Only actual reviewed tool results determine verification state.",
        }

    @staticmethod
    def _compact_tool(row: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(row, ensure_ascii=False, default=str)
        if len(raw) <= 12_000:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        return {
            "tool_name": row.get("tool_name"),
            "status": row.get("status"),
            "detail": row.get("detail"),
            "truncated": raw[:12_000],
        }
