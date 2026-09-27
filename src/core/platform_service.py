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
from .research_provider import GuardedResearchProvider
from .specialist_runtime import SpecialistRuntime
from .specialist_council import SpecialistCouncil
from .llm_chat import AIChatEngine
from .aivy_identity import AIVY
from .evolution_engine import VerifiedEvolutionEngine


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
        self.research_provider = GuardedResearchProvider()
        self.evolution = VerifiedEvolutionEngine()
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
                "guarded_web_research": True,
                "model_router": True,
                "specialist_consultation": True,
                "multimodal_design_review": True,
                "automatic_screenshot_capture": True,
                "specialist_council": True,
                "verified_evolution_engine": True,
            },
        }

    def specialist_agents(self) -> list[dict[str, Any]]:
        return self.specialists.public_contract()

    def model_routes(self) -> dict[str, Any]:
        tasks = {
            "fast": "classification",
            "reasoning": "reasoning",
            "coding": "coding",
            "vision": "visual",
            "research": "research",
            "security": "security",
        }
        settings = self.ai_engine.settings()
        default_status = self.ai_engine.status()
        rows = []
        for capability, task in tasks.items():
            configured = self.ai_engine.route_config(capability)
            effective = self.model_router.route(task)
            rows.append({
                "capability": capability,
                "configured": configured,
                "effective": effective.to_dict(),
            })
        return {
            "default": {
                "provider": str(settings.get("provider") or "none"),
                "model": str(settings.get("model") or ""),
                "connected": bool(default_status.connected),
            },
            "routes": rows,
        }

    def configure_model_route(self, capability: str, provider: str, model: str = "") -> dict[str, Any]:
        self.ai_engine.configure_route(capability, provider, model)
        return self.model_routes()

    def evolution_policy(self) -> dict[str, Any]:
        return {
            "policy": self.evolution.policy.to_dict(),
            "protected_paths": sorted([
                "src/core/safety.py",
                "src/core/permissions.py",
                "src/core/approval.py",
                "src/core/agent_tools.py",
                "src/core/agent_runtime.py",
                "src/tools/security_selfcheck.py",
                ".github/workflows/*",
            ]),
            "rule": "Aivy may compare self-improvements, but eligible candidates still require human review and can never auto-merge main.",
        }

    def compare_evolution_candidate(
        self,
        *,
        baseline: dict[str, Any],
        candidate: dict[str, Any],
        changed_paths: list[str],
        evidence_refs: list[str],
        requested_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        decision = self.evolution.compare(
            self.evolution.report_from_dict(baseline),
            self.evolution.report_from_dict(candidate),
            changed_paths=changed_paths,
            evidence_refs=evidence_refs,
            requested_actions=requested_actions or [],
        )
        return decision.to_dict()

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

    def run_specialist_council(
        self,
        goal: str,
        *,
        project_slug: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        council = SpecialistCouncil(
            engine=self.ai_engine,
            tools=self.tools,
            specialists=self.specialists,
            router=self.model_router,
        )
        combined = dict(context or {})
        combined["verified_agent_context"] = self.agent.context(goal)
        if project_slug:
            combined["project_slug"] = project_slug
            try:
                combined["project_detail"] = self.project_detail(project_slug)
            except FileNotFoundError:
                combined["project_detail"] = {"status": "not_found"}
        return council.run(goal, context=combined).to_dict()

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

    def fetch_research_source(self, url: str) -> dict[str, Any]:
        return self.research_provider.fetch(url).to_dict()

    def list_project_cards(self) -> list[dict[str, Any]]:
        return [asdict(x) for x in self.catalog.list_cards()]

    def project_detail(self, slug: str) -> dict[str, Any]:
        return self.catalog.detail(slug)

    def list_conversations(self, query: str = "") -> list[dict[str, Any]]:
        return [asdict(x) for x in self.conversations.list_threads(query)]

    def conversation_messages(self, thread_id: str) -> list[dict[str, str]]:
        return self.conversations.messages(thread_id)

    def chat_turn(self, thread_id: str, text: str) -> dict[str, Any]:
        clean = text.strip()
        if not clean:
            raise ValueError("message is required")
        thread = self.conversations.get(thread_id)
        if thread is None:
            raise KeyError(thread_id)

        if thread.project_slug:
            slug = thread.project_slug
            project_dir = safe_child(WORKSPACE_DIR, slug)
            if not project_dir.is_dir():
                raise FileNotFoundError(slug)
            meta = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
            project_name = str(meta.get("name") or slug)
            has_generated = (project_dir / "app_spec.json").is_file()
        else:
            opening = self.chat.opening_response(clean)
            if opening is not None:
                self.conversations.append(thread_id, "user", clean)
                self.conversations.append(thread_id, "assistant", opening)
                return {
                    "action": "chat",
                    "message": opening,
                    "instruction": None,
                    "project_slug": None,
                    "thread": asdict(self.conversations.get(thread_id)),
                }

            project_name = self.chat.suggest_project_name(clean)
            prior_rows = self.conversations.messages(thread_id)
            created = self.create_project(project_name, thread_id)
            slug = str(created["slug"])
            project_dir = safe_child(WORKSPACE_DIR, slug)
            for row in prior_rows:
                self.chat.append_external_message(
                    project_dir,
                    str(row.get("role") or "user"),
                    str(row.get("content") or ""),
                )
            has_generated = False

        decision = self.chat.handle(
            project_dir,
            project_name,
            slug,
            clean,
            has_generated=has_generated,
        )
        self.conversations.append(thread_id, "user", clean)
        self.conversations.append(thread_id, "assistant", decision.message)
        current = self.conversations.get(thread_id)
        return {
            "action": decision.action,
            "message": decision.message,
            "instruction": decision.instruction,
            "project_slug": slug,
            "thread": asdict(current) if current else None,
        }

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
        thread_id: str | None = None,
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
        if thread_id:
            self.conversations.append(thread_id, "assistant", result.message)
            try:
                self.chat.append_external_message(project_dir, "assistant", result.message)
            except Exception:
                pass
        return result

    @staticmethod
    def core_result_dict(result: CoreResult) -> dict[str, Any]:
        return {
            "ok": result.ok,
            "message": result.message,
            "safety": asdict(result.safety),
            "files": [str(x) for x in result.files],
            "tests": [asdict(x) for x in result.tests],
            "plan": result.plan,
            "risk_items": result.risk_items or [],
            "design_review": result.design_review.to_dict() if result.design_review else None,
            "capability_gaps": [asdict(x) for x in (result.capability_gaps or [])],
            "lessons_used": result.lessons_used or [],
            "pipeline_report": result.pipeline_report or {},
            "ai_enhancement": result.ai_enhancement or {},
            "repair_attempts": result.repair_attempts or [],
            "windows_build": result.windows_build,
            "web_build": result.web_build,
            "android_build": result.android_build,
        }

    def delivery_options(self, slug: str) -> list[dict[str, Any]]:
        return [asdict(x) for x in self.catalog.delivery_options(slug)]
