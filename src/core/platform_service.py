from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable
import json

from .ai_core import AICore, CoreResult
from .agent_runtime import AgentOrchestrator, EvidenceLedger
from .chat_partner import ChatPartner
from .config import WORKSPACE_DIR
from .database import list_projects
from .path_security import safe_child
from .project_manager import ProjectManager
from .workspace_catalog import ConversationStore, ProjectCatalog
from .agent_tools import AgentToolRegistry
from .specialist_agents import SpecialistAgentRegistry
from .model_router import ModelRouter
from .knowledge_store import VerifiedKnowledgeStore
from .research_guard import ResearchIntake
from .specialist_runtime import SpecialistRuntime
from .llm_chat import AIChatEngine
from .aivy_identity import AIVY


class PlatformService:
    """UI-independent application service.

    Tkinter, a future React/Tauri desktop shell, CLI, or a local API should talk
    to this facade instead of importing UI internals.
    """

    def __init__(self):
        self.projects = ProjectManager()
        self.catalog = ProjectCatalog()
        self.conversations = ConversationStore()
        self.chat = ChatPartner()
        self.core = AICore()
        self.tools = AgentToolRegistry()
        self.specialists = SpecialistAgentRegistry(self.tools)
        self.ai_engine = AIChatEngine()
        self.model_router = ModelRouter(self.ai_engine)
        self.knowledge = VerifiedKnowledgeStore()
        self.research = ResearchIntake(self.knowledge)
        self.agent = AgentOrchestrator(
            tools=self.tools,
            specialists=self.specialists,
            model_router=self.model_router,
            knowledge=self.knowledge,
        )

    def status(self) -> dict[str, Any]:
        return {
            "service": "ai-app-platform",
            "identity": AIVY.to_dict(),
            "architecture": "local-first-core-service",
            "project_count": len(list_projects()),
            "capabilities": {
                "web": True,
                "windows": True,
                "android": True,
                "ios_source": True,
                "social_automation": True,
                "persistent_conversations": True,
                "artifact_catalog": True,
                "agent_planning": True,
                "registered_agent_tools": len(self.tools.list()),
                "specialist_agents": len(self.specialists.list()),
                "verified_knowledge": True,
                "model_router": True,
                "specialist_consultation": True,
            },
        }

    def specialist_agents(self) -> list[dict[str, Any]]:
        return self.specialists.public_contract()

    def consult_specialist(
        self,
        specialist_name: str,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        runtime = SpecialistRuntime(
            engine=self.ai_engine,
            registry=self.specialists,
            router=self.model_router,
        )
        return runtime.consult(
            specialist_name,
            task,
            context or {},
        ).to_dict()

    def agent_context(self, goal: str) -> dict[str, Any]:
        return self.agent.context(goal)

    def verified_knowledge(self, query: str = "") -> list[dict[str, Any]]:
        rows = self.knowledge.search(query, verified_only=True) if query.strip() else self.knowledge.list("verified")
        return [x.to_dict() for x in rows]

    def research_intake(
        self,
        *,
        topic: str,
        statement: str,
        sources: list[dict[str, str]],
    ) -> dict[str, Any]:
        return self.research.submit_claim(
            topic=topic,
            statement=statement,
            sources=sources,
        ).to_dict()

    def list_project_cards(self) -> list[dict[str, Any]]:
        return [asdict(x) for x in self.catalog.list_cards()]

    def project_detail(self, slug: str) -> dict[str, Any]:
        return self.catalog.detail(slug)

    def list_conversations(self, query: str = "") -> list[dict[str, Any]]:
        return [asdict(x) for x in self.conversations.list_threads(query)]

    def conversation_messages(self, thread_id: str) -> list[dict[str, str]]:
        return self.conversations.messages(thread_id)

    def create_conversation(self, title: str = "新しいチャット") -> dict[str, Any]:
        thread_id = self.conversations.create_thread(title)
        row = self.conversations.get(thread_id)
        if row is None:
            raise RuntimeError("conversation creation failed")
        return asdict(row)

    def create_project(self, name: str, thread_id: str | None = None) -> dict[str, Any]:
        slug, path = self.projects.create(name)
        if thread_id:
            self.conversations.link_project(thread_id, slug, name)
        return {"name": name, "slug": slug, "path": str(path)}

    def agent_plan(self, goal: str, project_slug: str | None = None) -> dict[str, Any]:
        return self.agent.plan(goal, project_slug).to_dict()

    def build_project(
        self,
        slug: str,
        instruction: str,
        *,
        approved: bool,
        progress: Callable[[str, str], None] | None = None,
    ) -> CoreResult:
        if not approved:
            raise PermissionError("explicit user approval is required before generation")
        project_dir = safe_child(WORKSPACE_DIR, slug)
        if not project_dir.is_dir():
            raise FileNotFoundError(slug)
        meta = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
        project_name = str(meta.get("name") or slug)

        plan = self.agent.plan(instruction, slug)
        ledger = EvidenceLedger(project_dir)
        ledger.record(
            run_id=plan.run_id,
            stage="plan",
            status="ready",
            summary=f"{len(plan.steps)} bounded agent steps prepared",
            source="agent-orchestrator",
        )

        result = self.core.execute(project_name, slug, project_dir, instruction, progress)
        ledger.record(
            run_id=plan.run_id,
            stage="validate",
            status="pass" if result.ok else "blocked",
            summary=result.message,
            source="ai-core",
        )
        if result.ok:
            ledger.record(
                run_id=plan.run_id,
                stage="report",
                status="verified",
                summary="generation completed with platform quality gates satisfied",
                source="generation-pipeline",
            )
        return result

    def delivery_options(self, slug: str) -> list[dict[str, Any]]:
        return [asdict(x) for x in self.catalog.delivery_options(slug)]
