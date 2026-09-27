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

        configured = None
        if hasattr(self.engine, "route_config"):
            try:
                configured = self.engine.route_config(capability)
            except Exception:
                configured = None

        if configured:
            provider = str(configured.get("provider") or "")
            model = str(configured.get("model") or "")
            try:
                status = self.engine.status(provider, model)
            except TypeError:
                status = self.engine.status()
            if status.connected:
                return ModelRoute(
                    task=task,
                    mode="capability_route",
                    provider=provider,
                    model=model,
                    capability=capability,
                    reason=f"Capability '{capability}' is explicitly routed to {provider}/{model}.",
                )

        status = self.engine.status()
        if hasattr(self.engine, "settings"):
            try:
                settings = self.engine.settings()
            except Exception:
                settings = {}
        else:
            settings = {}
        if not status.connected:
            return ModelRoute(
                task=task,
                mode="deterministic_fallback",
                provider="none",
                model="",
                capability=capability,
                reason="No external AI provider is connected; use deterministic platform logic where supported.",
            )
        provider = str(settings.get("provider") or getattr(status, "provider", "") or "legacy")
        model = str(settings.get("model") or getattr(status, "model", "") or "")
        return ModelRoute(
            task=task,
            mode="configured_provider",
            provider=provider,
            model=model,
            capability=capability,
            reason="No capability-specific route is active, so Aivy uses the configured default provider/model.",
        )
