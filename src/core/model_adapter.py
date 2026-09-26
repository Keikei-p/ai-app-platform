from __future__ import annotations
from abc import ABC, abstractmethod

class ModelAdapter(ABC):
    """Pluggable reasoning/model interface. Safety and permissions sit outside this adapter."""
    @abstractmethod
    def plan(self, instruction: str, project_context: dict) -> dict:
        raise NotImplementedError

class RuleBasedModelAdapter(ModelAdapter):
    def plan(self, instruction: str, project_context: dict) -> dict:
        return {
            "goal": instruction.strip(),
            "steps": ["snapshot", "generate_or_modify", "test", "record_audit"],
            "adapter": "rule-based-v0.2",
        }
