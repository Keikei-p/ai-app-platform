from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .llm_chat import AIChatEngine


@dataclass(frozen=True)
class ModelRoute:
    task: str
    mode: str
    provider: str
    model: str
    capability: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelRouter:
    """Task-aware model-routing contract.

    v0.9 still uses the user's configured provider/model. This router makes the
    decision explicit now so per-task provider/model overrides can be added later
    without changing specialist-agent contracts.
    """

    TASK_CAPABILITY = {
        "classification": "fast",
        "summarization": "fast",
        "research": "reasoning",
        "reasoning": "reasoning",
        "coding": "coding",
        "analysis": "reasoning",
        "visual": "vision",
        "security": "reasoning",
    }

    def __init__(self, engine: AIChatEngine | None = None):
        self.engine = engine or AIChatEngine()

    def route(self, task: str) -> ModelRoute:
        task = task.strip().lower()
        capability = self.TASK_CAPABILITY.get(task, "reasoning")
        status = self.engine.status()
        settings = self.engine.settings()
        if not status.connected:
            return ModelRoute(
                task=task,
                mode="deterministic_fallback",
                provider="none",
                model="",
                capability=capability,
                reason="No external AI provider is connected; use deterministic platform logic where supported.",
            )
        return ModelRoute(
            task=task,
            mode="configured_provider",
            provider=str(settings.get("provider") or ""),
            model=str(settings.get("model") or ""),
            capability=capability,
            reason=(
                "v0.9 routes the specialist task through the currently configured provider/model. "
                "Per-task overrides are reserved for a later model-router milestone."
            ),
        )
