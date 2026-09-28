from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AivyHealthDashboard:
    project_count: int
    specialist_count: int
    mission_count: int
    active_missions: int
    verified_learning_examples: int
    average_learning_score: float
    model_observations: int
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_count": self.project_count,
            "specialist_count": self.specialist_count,
            "mission_count": self.mission_count,
            "active_missions": self.active_missions,
            "verified_learning_examples": self.verified_learning_examples,
            "average_learning_score": self.average_learning_score,
            "model_observations": self.model_observations,
            "status": self.status,
        }
