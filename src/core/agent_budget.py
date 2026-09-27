from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class AgentBudget:
    max_model_calls: int = 12
    max_research_sources: int = 8
    max_tool_calls: int = 16
    max_repair_attempts: int = 2
    max_specialist_output_chars: int = 12_000

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentBudgetTracker:
    def __init__(self, budget: AgentBudget | None = None):
        self.budget = budget or AgentBudget()
        self.model_calls = 0
        self.research_sources = 0
        self.tool_calls = 0
        self._lock = Lock()

    def reserve_model_call(self) -> int:
        with self._lock:
            if self.model_calls >= self.budget.max_model_calls:
                raise RuntimeError("agent model-call budget exceeded")
            self.model_calls += 1
            return self.model_calls

    def reserve_research_sources(self, count: int) -> int:
        count = max(0, int(count))
        with self._lock:
            if self.research_sources + count > self.budget.max_research_sources:
                raise RuntimeError("agent research-source budget exceeded")
            self.research_sources += count
            return self.research_sources

    def reserve_tool_call(self) -> int:
        with self._lock:
            if self.tool_calls >= self.budget.max_tool_calls:
                raise RuntimeError("agent tool-call budget exceeded")
            self.tool_calls += 1
            return self.tool_calls

    def snapshot(self) -> dict[str, Any]:
        return {
            "budget": self.budget.to_dict(),
            "used": {
                "model_calls": self.model_calls,
                "research_sources": self.research_sources,
                "tool_calls": self.tool_calls,
            },
        }
