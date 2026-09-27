from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AgentToolDefinition:
    name: str
    purpose: str
    risk: str
    requires_human_approval: bool
    read_scope: tuple[str, ...]
    write_scope: tuple[str, ...]
    evidence_stage: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["read_scope"] = list(self.read_scope)
        data["write_scope"] = list(self.write_scope)
        return data


class AgentToolRegistry:
    """Explicit allowlist of agent capabilities.

    Registry entries are metadata/contracts only. Actual execution stays inside
    reviewed platform engines rather than model-created command strings.
    """

    def __init__(self):
        self._tools = {
            tool.name: tool
            for tool in (
                AgentToolDefinition(
                    "project.inspect",
                    "Read project metadata, specs, reports and prior verified history.",
                    "low",
                    False,
                    ("project", "reports", "history"),
                    (),
                    "inspect",
                ),
                AgentToolDefinition(
                    "knowledge.search",
                    "Read only verified technical knowledge relevant to the current development goal.",
                    "low",
                    False,
                    ("verified_knowledge",),
                    (),
                    "inspect",
                ),
                AgentToolDefinition(
                    "research.intake",
                    "Inspect externally supplied research text and quarantine prompt-injection indicators before knowledge ingestion.",
                    "medium",
                    False,
                    ("external_untrusted_text",),
                    ("untrusted_knowledge",),
                    "inspect",
                ),
                AgentToolDefinition(
                    "vault.snapshot",
                    "Create a restorable project checkpoint before AI changes.",
                    "low",
                    False,
                    ("project",),
                    ("vault",),
                    "inspect",
                ),
                AgentToolDefinition(
                    "code.generate",
                    "Generate or modify allowed source files through bounded generators/coding brain.",
                    "medium",
                    False,
                    ("project", "spec", "verified_memory"),
                    ("project_source",),
                    "generate",
                ),
                AgentToolDefinition(
                    "tests.run",
                    "Run the approved project test runner and record deterministic results.",
                    "low",
                    False,
                    ("project_source",),
                    ("reports",),
                    "validate",
                ),
                AgentToolDefinition(
                    "design.review",
                    "Evaluate generated UI against Design AI quality rules.",
                    "low",
                    False,
                    ("project_source",),
                    ("reports",),
                    "validate",
                ),
                AgentToolDefinition(
                    "security.scan",
                    "Scan generated artifacts for secrets, dangerous code and release blockers.",
                    "low",
                    False,
                    ("project_source", "dependencies"),
                    ("reports",),
                    "validate",
                ),
                AgentToolDefinition(
                    "code.repair",
                    "Apply bounded repairs from verified failure evidence.",
                    "medium",
                    False,
                    ("project_source", "reports", "verified_memory"),
                    ("project_source",),
                    "repair",
                ),
                AgentToolDefinition(
                    "package.build",
                    "Build verified Web/Windows/mobile artifacts when supported.",
                    "medium",
                    False,
                    ("project_source", "reports"),
                    ("artifacts",),
                    "package",
                ),
                AgentToolDefinition(
                    "artifact.export",
                    "Copy an existing verified artifact to a user-selected destination.",
                    "medium",
                    True,
                    ("artifacts",),
                    ("user_selected_destination",),
                    "review",
                ),
                AgentToolDefinition(
                    "release.publish",
                    "Publish/deploy externally using a configured approved release adapter.",
                    "high",
                    True,
                    ("artifacts", "release_config"),
                    ("external_service",),
                    "review",
                ),
                AgentToolDefinition(
                    "store.submit",
                    "Submit a signed app to an external app store.",
                    "high",
                    True,
                    ("signed_artifact", "store_config"),
                    ("external_store",),
                    "review",
                ),
            )
        }

    def get(self, name: str) -> AgentToolDefinition:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"unregistered agent tool: {name}")
        return tool

    def list(self) -> list[AgentToolDefinition]:
        return list(self._tools.values())

    def public_contract(self) -> list[dict[str, Any]]:
        return [x.to_dict() for x in self.list()]

    def requires_approval(self, name: str) -> bool:
        return self.get(name).requires_human_approval
