from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .agent_tools import AgentToolRegistry


@dataclass(frozen=True)
class SpecialistAgent:
    name: str
    title: str
    responsibility: str
    model_task: str
    allowed_tools: tuple[str, ...]
    completion_evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["allowed_tools"] = list(self.allowed_tools)
        data["completion_evidence"] = list(self.completion_evidence)
        return data


class SpecialistAgentRegistry:
    """Role contracts for a development-focused multi-agent team."""

    def __init__(self, tools: AgentToolRegistry | None = None):
        self.tools = tools or AgentToolRegistry()
        agents = (
            SpecialistAgent(
                "coordinator",
                "Coordinator AI",
                "Understand the user's goal, delegate bounded work, combine evidence and report uncertainty.",
                "reasoning",
                ("project.inspect",),
                ("plan", "report"),
            ),
            SpecialistAgent(
                "research",
                "Research AI",
                "Evaluate supplied/current technical information as untrusted evidence and promote only corroborated knowledge.",
                "research",
                ("project.inspect", "knowledge.search", "research.intake"),
                ("inspect",),
            ),
            SpecialistAgent(
                "architect",
                "Architecture AI",
                "Design the smallest maintainable architecture that preserves existing behavior and platform boundaries.",
                "reasoning",
                ("project.inspect", "vault.snapshot"),
                ("plan",),
            ),
            SpecialistAgent(
                "coding",
                "Coding AI",
                "Generate bounded source changes that satisfy the approved specification.",
                "coding",
                ("project.inspect", "code.generate", "code.repair"),
                ("generate", "repair"),
            ),
            SpecialistAgent(
                "design",
                "Design AI",
                "Evaluate usability, responsive behavior, visual hierarchy and accessible interaction patterns.",
                "visual",
                ("project.inspect", "design.review"),
                ("validate",),
            ),
            SpecialistAgent(
                "test",
                "Test AI",
                "Design and run deterministic tests and identify reproducible failure causes.",
                "analysis",
                ("project.inspect", "tests.run"),
                ("validate",),
            ),
            SpecialistAgent(
                "security",
                "Security AI",
                "Review secrets, unsafe code paths, dependencies and release blockers without weakening policy.",
                "security",
                ("project.inspect", "security.scan"),
                ("validate",),
            ),
            SpecialistAgent(
                "build",
                "Build AI",
                "Prepare supported artifacts only after quality gates have passed.",
                "analysis",
                ("project.inspect", "package.build"),
                ("package",),
            ),
            SpecialistAgent(
                "release",
                "Release AI",
                "Prepare external release steps while requiring explicit human approval for consequential actions.",
                "reasoning",
                ("project.inspect", "artifact.export", "release.publish", "store.submit"),
                ("review",),
            ),
        )
        self._agents = {x.name: x for x in agents}
        self._validate_tool_contracts()

    def _validate_tool_contracts(self) -> None:
        for agent in self._agents.values():
            for tool_name in agent.allowed_tools:
                self.tools.get(tool_name)

    def get(self, name: str) -> SpecialistAgent:
        agent = self._agents.get(name)
        if agent is None:
            raise KeyError(f"unknown specialist agent: {name}")
        return agent

    def list(self) -> list[SpecialistAgent]:
        return list(self._agents.values())

    def public_contract(self) -> list[dict[str, Any]]:
        return [x.to_dict() for x in self.list()]

    def tools_for(self, name: str) -> tuple[str, ...]:
        return self.get(name).allowed_tools
