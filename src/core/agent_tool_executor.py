from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json

from .agent_runtime import EvidenceLedger
from .agent_tools import AgentToolRegistry
from .config import WORKSPACE_DIR
from .design_ai import DesignAI
from .evolution_engine import VerifiedEvolutionEngine
from .generation_pipeline import GeneratedArtifactSecurityScanner
from .knowledge_store import VerifiedKnowledgeStore
from .path_security import safe_child
from .project_manager import ProjectManager
from .research_provider import GuardedResearchProvider
from .test_runner import ProjectTestRunner
from .workspace_catalog import ProjectCatalog


@dataclass(frozen=True)
class AgentToolExecution:
    tool_name: str
    status: str
    evidence_stage: str
    approval_required: bool
    result: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentToolExecutor:
    """Execute only reviewed, explicitly bound Agent Tool Registry operations.

    This class intentionally has no generic shell/process/command execution path.
    Registered metadata alone does not make a tool executable: a reviewed handler
    must also exist in this class. Every binding also has an exact argument allowlist.
    """

    ARG_ALLOWLIST = {
        "project.inspect": {"project_slug"},
        "knowledge.search": {"query", "limit"},
        "research.fetch": {"url"},
        "vault.snapshot": {"project_slug", "label"},
        "tests.run": {"project_slug"},
        "design.review": {"project_slug"},
        "security.scan": {"project_slug"},
        "evolution.compare": {
            "baseline", "candidate", "changed_paths", "evidence_refs", "requested_actions",
        },
    }

    def __init__(
        self,
        *,
        registry: AgentToolRegistry | None = None,
        catalog: ProjectCatalog | None = None,
        knowledge: VerifiedKnowledgeStore | None = None,
        research: GuardedResearchProvider | None = None,
        projects: ProjectManager | None = None,
        tests: ProjectTestRunner | None = None,
        design: DesignAI | None = None,
        security: GeneratedArtifactSecurityScanner | None = None,
        evolution: VerifiedEvolutionEngine | None = None,
    ):
        self.registry = registry or AgentToolRegistry()
        self.catalog = catalog or ProjectCatalog()
        self.knowledge = knowledge or VerifiedKnowledgeStore()
        self.research = research or GuardedResearchProvider()
        self.projects = projects or ProjectManager()
        self.tests = tests or ProjectTestRunner()
        self.design = design or DesignAI()
        self.security = security or GeneratedArtifactSecurityScanner()
        self.evolution = evolution or VerifiedEvolutionEngine()
        self._handlers = {
            "project.inspect": self._project_inspect,
            "knowledge.search": self._knowledge_search,
            "research.fetch": self._research_fetch,
            "vault.snapshot": self._vault_snapshot,
            "tests.run": self._tests_run,
            "design.review": self._design_review,
            "security.scan": self._security_scan,
            "evolution.compare": self._evolution_compare,
        }

    def executable_tools(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def execute(
        self,
        tool_name: str,
        args: dict[str, Any] | None = None,
        *,
        approved: bool = False,
        run_id: str = "tool-execution",
    ) -> AgentToolExecution:
        definition = self.registry.get(tool_name)
        if definition.requires_human_approval and not approved:
            raise PermissionError(f"human approval required for tool: {tool_name}")
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise PermissionError(f"registered tool has no reviewed executor binding: {tool_name}")

        payload = dict(args or {})
        self._reject_execution_smuggling(payload)
        self._validate_args(tool_name, payload)
        result = handler(payload)
        if not isinstance(result, dict):
            result = {"value": result}

        project_slug = str(payload.get("project_slug") or "").strip()
        if project_slug:
            project_dir = self._project_dir(project_slug)
            ledger = EvidenceLedger(project_dir)
            evidence_status = self._evidence_status(tool_name, result)
            ledger.record(
                run_id=run_id,
                stage=definition.evidence_stage,
                status=evidence_status,
                summary=f"reviewed tool executed: {tool_name} ({evidence_status})",
                source="agent-tool-executor",
            )

        return AgentToolExecution(
            tool_name=tool_name,
            status="executed",
            evidence_stage=definition.evidence_stage,
            approval_required=definition.requires_human_approval,
            result=result,
        )

    @staticmethod
    def _reject_execution_smuggling(payload: dict[str, Any]) -> None:
        forbidden_keys = {
            "shell", "command", "cmd", "powershell", "bash", "executable",
            "process", "subprocess", "argv",
        }
        for key in payload:
            if str(key).strip().lower() in forbidden_keys:
                raise ValueError("generic execution arguments are not allowed")

    def _validate_args(self, tool_name: str, payload: dict[str, Any]) -> None:
        allowed = self.ARG_ALLOWLIST.get(tool_name)
        if allowed is None:
            raise PermissionError(f"tool has no reviewed argument schema: {tool_name}")
        unknown = sorted(str(key) for key in payload if str(key) not in allowed)
        if unknown:
            raise ValueError("unsupported tool arguments: " + ", ".join(unknown))

    @staticmethod
    def _evidence_status(tool_name: str, result: dict[str, Any]) -> str:
        if tool_name == "tests.run":
            return "pass" if bool(result.get("passed")) else "fail"
        if tool_name == "design.review":
            return "pass" if bool((result.get("review") or {}).get("passed")) else "fail"
        if tool_name == "security.scan":
            return "pass" if bool((result.get("security") or {}).get("passed")) else "fail"
        return "pass"

    @staticmethod
    def _project_dir(slug: str) -> Path:
        path = safe_child(WORKSPACE_DIR, slug)
        if not path.is_dir():
            raise FileNotFoundError(slug)
        return path

    def _project_inspect(self, args: dict[str, Any]) -> dict[str, Any]:
        slug = str(args.get("project_slug") or "").strip()
        if not slug:
            raise ValueError("project_slug is required")
        return self.catalog.detail(slug)

    def _knowledge_search(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        limit = max(1, min(int(args.get("limit") or 8), 20))
        rows = self.knowledge.search(query, verified_only=True, limit=limit)
        return {"knowledge": [x.to_dict() for x in rows]}

    def _research_fetch(self, args: dict[str, Any]) -> dict[str, Any]:
        url = str(args.get("url") or "").strip()
        if not url:
            raise ValueError("url is required")
        return self.research.fetch(url).to_dict()

    def _vault_snapshot(self, args: dict[str, Any]) -> dict[str, Any]:
        slug = str(args.get("project_slug") or "").strip()
        if not slug:
            raise ValueError("project_slug is required")
        label = str(args.get("label") or "agent-checkpoint").strip()[:120]
        path = self.projects.snapshot(slug, label)
        return {"snapshot": str(path)}

    def _tests_run(self, args: dict[str, Any]) -> dict[str, Any]:
        slug = str(args.get("project_slug") or "").strip()
        project_dir = self._project_dir(slug)
        rows = self.tests.run(project_dir)
        return {
            "passed": bool(rows) and all(x.passed for x in rows),
            "results": [asdict(x) for x in rows],
        }

    def _design_review(self, args: dict[str, Any]) -> dict[str, Any]:
        slug = str(args.get("project_slug") or "").strip()
        project_dir = self._project_dir(slug)
        review = self.design.review(project_dir)
        report_path = self.design.save(project_dir, review)
        return {"review": review.to_dict(), "report": str(report_path)}

    def _security_scan(self, args: dict[str, Any]) -> dict[str, Any]:
        slug = str(args.get("project_slug") or "").strip()
        project_dir = self._project_dir(slug)
        report = self.security.scan(project_dir)
        path = project_dir / ".aiapp" / "reports" / "security_scan_ad_hoc.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return {"security": report.to_dict(), "report": str(path)}

    def _evolution_compare(self, args: dict[str, Any]) -> dict[str, Any]:
        baseline = args.get("baseline")
        candidate = args.get("candidate")
        changed_paths = args.get("changed_paths")
        evidence_refs = args.get("evidence_refs")
        if not isinstance(baseline, dict) or not isinstance(candidate, dict):
            raise ValueError("baseline and candidate reports are required")
        if not isinstance(changed_paths, list) or not isinstance(evidence_refs, list):
            raise ValueError("changed_paths and evidence_refs must be arrays")
        decision = self.evolution.compare(
            self.evolution.report_from_dict(baseline),
            self.evolution.report_from_dict(candidate),
            changed_paths=[str(x) for x in changed_paths],
            evidence_refs=[str(x) for x in evidence_refs],
            requested_actions=[str(x) for x in (args.get("requested_actions") or [])],
        )
        return {"decision": decision.to_dict()}
