from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
import uuid

from .agent_tool_executor import AgentToolExecutor


@dataclass(frozen=True)
class ProjectHealthReport:
    run_id: str
    project_slug: str
    status: str
    tests_passed: bool
    design_passed: bool
    security_passed: bool
    checks: tuple[dict[str, Any], ...]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checks"] = list(self.checks)
        return data


class ProjectHealthCheck:
    """Re-run non-destructive quality checks through the reviewed tool executor."""

    CHECKS = ("tests.run", "design.review", "security.scan")

    def __init__(self, executor: AgentToolExecutor):
        self.executor = executor

    def run(self, project_slug: str) -> ProjectHealthReport:
        slug = project_slug.strip()
        if not slug:
            raise ValueError("project_slug is required")
        run_id = "health-" + uuid.uuid4().hex
        rows: list[dict[str, Any]] = []

        for tool_name in self.CHECKS:
            result = self.executor.execute(
                tool_name,
                {"project_slug": slug},
                run_id=run_id,
            )
            rows.append(result.to_dict())

        tests = next(x["result"] for x in rows if x["tool_name"] == "tests.run")
        design = next(x["result"] for x in rows if x["tool_name"] == "design.review")
        security = next(x["result"] for x in rows if x["tool_name"] == "security.scan")

        tests_passed = bool(tests.get("passed"))
        design_passed = bool((design.get("review") or {}).get("passed"))
        security_passed = bool((security.get("security") or {}).get("passed"))
        passed = tests_passed and design_passed and security_passed

        return ProjectHealthReport(
            run_id=run_id,
            project_slug=slug,
            status="pass" if passed else "attention_required",
            tests_passed=tests_passed,
            design_passed=design_passed,
            security_passed=security_passed,
            checks=tuple(rows),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
