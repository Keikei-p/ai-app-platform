from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TaskNode:
    task_id: str
    title: str
    role: str
    depends_on: tuple[str, ...]
    stage: str
    approval_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["depends_on"] = list(self.depends_on)
        return data


@dataclass(frozen=True)
class TaskGraph:
    goal: str
    nodes: tuple[TaskNode, ...]
    waves: tuple[tuple[str, ...], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "nodes": [x.to_dict() for x in self.nodes],
            "waves": [list(x) for x in self.waves],
        }


class TaskGraphPlanner:
    """Deterministic dependency graph for Aivy specialist work."""

    def build(self, goal: str, squad: dict[str, Any]) -> TaskGraph:
        clean = goal.strip()
        if not clean:
            raise ValueError("goal is required")
        roles = set(str(x) for x in squad.get("roles") or ())

        nodes: list[TaskNode] = [
            TaskNode("inspect", "Inspect project and verified memory", "architect", (), "inspect"),
        ]
        if "research" in roles:
            nodes.append(TaskNode("research", "Resolve current facts and unknowns", "research", (), "inspect"))
        plan_deps = tuple(x.task_id for x in nodes if x.task_id in {"inspect", "research"})
        nodes.append(TaskNode("architecture", "Produce bounded implementation plan", "architect", plan_deps, "plan"))

        for role, task_id, title in (
            ("database", "database-plan", "Review data model and migrations"),
            ("web", "web-plan", "Review web architecture"),
            ("mobile", "mobile-plan", "Review mobile architecture"),
            ("accessibility", "a11y-plan", "Review accessibility requirements"),
            ("performance", "performance-plan", "Review performance budgets"),
            ("devops", "devops-plan", "Review delivery and runtime operations"),
        ):
            if role in roles:
                nodes.append(TaskNode(task_id, title, role, ("architecture",), "plan"))

        specialist_plan_ids = tuple(
            x.task_id for x in nodes if x.stage == "plan" and x.task_id != "architecture"
        )
        generate_deps = ("architecture", *specialist_plan_ids)
        nodes.append(TaskNode("generate", "Generate bounded source changes", "coding", generate_deps, "generate"))

        validation_nodes = [
            TaskNode("tests", "Run deterministic tests", "test", ("generate",), "validate"),
            TaskNode("security", "Run security verification", "security", ("generate",), "validate"),
        ]
        if "design" in roles or "web" in roles or "mobile" in roles:
            validation_nodes.append(TaskNode("design", "Review UI and responsive quality", "design", ("generate",), "validate"))
        if "accessibility" in roles:
            validation_nodes.append(TaskNode("accessibility", "Run accessibility guardian", "accessibility", ("generate",), "validate"))
        if "performance" in roles:
            validation_nodes.append(TaskNode("performance", "Run performance guardian", "performance", ("generate",), "validate"))
        if "database" in roles:
            validation_nodes.append(TaskNode("database-verify", "Verify persistence and migration safety", "database", ("generate",), "validate"))
        nodes.extend(validation_nodes)

        verify_ids = tuple(x.task_id for x in validation_nodes)
        nodes.append(TaskNode("review", "Compare evidence and regressions", "coordinator", verify_ids, "review"))
        if "build" in roles:
            nodes.append(TaskNode("package", "Build verified artifacts", "build", ("review",), "package"))
            release_dep = ("package",)
        else:
            release_dep = ("review",)
        if "release" in roles:
            nodes.append(TaskNode("release-gate", "Verify release readiness", "release", release_dep, "review", True))
        nodes.append(TaskNode("report", "Produce evidence-backed completion report", "coordinator", release_dep, "report"))

        return TaskGraph(clean, tuple(nodes), self._waves(nodes))

    @staticmethod
    def _waves(nodes: list[TaskNode]) -> tuple[tuple[str, ...], ...]:
        pending = {x.task_id: set(x.depends_on) for x in nodes}
        done: set[str] = set()
        waves: list[tuple[str, ...]] = []
        while pending:
            ready = tuple(sorted(k for k, deps in pending.items() if deps.issubset(done)))
            if not ready:
                raise ValueError("task graph contains a dependency cycle")
            waves.append(ready)
            for key in ready:
                pending.pop(key, None)
                done.add(key)
        return tuple(waves)
