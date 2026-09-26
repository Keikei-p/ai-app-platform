from __future__ import annotations
from dataclasses import dataclass, asdict
import json
from pathlib import Path

@dataclass(frozen=True)
class AppSpec:
    project_name: str
    slug: str
    summary: str
    app_type: str
    features: list[str]
    targets: list[str]
    language: str = "ja"
    region: str = "JP"
    risk_level: str = "normal"
    design_style: str = "modern"
    usage_context: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, project_dir: Path) -> Path:
        path = project_dir / "app_spec.json"
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

@dataclass(frozen=True)
class BuildStep:
    key: str
    label: str
    destructive: bool = False
    requires_approval: bool = False

@dataclass(frozen=True)
class AppPlan:
    spec: AppSpec
    steps: list[BuildStep]

    def to_dict(self) -> dict:
        return {"spec": self.spec.to_dict(), "steps": [asdict(x) for x in self.steps]}
