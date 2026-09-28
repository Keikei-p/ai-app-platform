from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable
import json

from .ai_core import AICore, CoreResult
from .agent_runtime import AgentOrchestrator, EvidenceLedger
from .checkpoint_manager import CheckpointManager
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
from .knowledge_factory import KnowledgeFactory
from .knowledge_imports import KnowledgeImportManager
from .knowledge_intelligence import KnowledgeSearchEngine
from .research_guard import ResearchIntake
from .research_provider import GuardedResearchProvider
from .specialist_runtime import SpecialistRuntime
from .specialist_council import SpecialistCouncil
from .specialist_execution_council import SpecialistExecutionCouncil
from .llm_chat import AIChatEngine
from .aivy_identity import AIVY
from .evolution_engine import VerifiedEvolutionEngine
from .evolution_experiments import EvolutionExperimentStore
from .build_jobs import BuildJobManager
from .agent_tool_executor import AgentToolExecutor
from .project_health import ProjectHealthCheck
from .agent_plan_runner import AgentPlanRunner
from .agent_execution_trace import BuildExecutionTracer
from .knowledge_verifier import ProjectKnowledgeVerifier
from .completion_certificate import DevelopmentCertificateBuilder
from .recovery_supervisor import RecoverySupervisor
from .secrets_guard import SecretsGuard
from .cost_guard import CostGuard
from .stop_escalation import StopEscalationJudge
from .production_monitor import HealthSample, ProductionMonitor


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
        self.knowledge_factory = KnowledgeFactory(self.knowledge)
        self.knowledge_imports = KnowledgeImportManager(self.knowledge_factory)
        self.knowledge_search = KnowledgeSearchEngine(self.knowledge)
        self.research = ResearchIntake(self.knowledge)
        self.research_provider = GuardedResearchProvider()
        self.evolution = VerifiedEvolutionEngine()
        self.evolution_experiments = EvolutionExperimentStore()
        self.knowledge_verifier = ProjectKnowledgeVerifier(self.knowledge)
        self.build_jobs = BuildJobManager()
        self.tool_executor = AgentToolExecutor(
            registry=self.tools,
            catalog=self.catalog,
            knowledge=self.knowledge,
            research=self.research_provider,
            projects=self.projects,
            evolution=self.evolution,
            project_resolver=lambda slug: safe_child(WORKSPACE_DIR, slug),
        )
        self.project_health_checker = ProjectHealthCheck(self.tool_executor)
        self.execution_council = SpecialistExecutionCouncil(
            engine=self.ai_engine,
            tools=self.tools,
            specialists=self.specialists,
            router=self.model_router,
            executor=self.tool_executor,
        )
        self.agent_plan_runner = AgentPlanRunner(self.tool_executor, registry=self.tools)
        self.build_execution_tracer = BuildExecutionTracer()
        self.development_certificates = DevelopmentCertificateBuilder()
        self.secrets_guard = SecretsGuard()
        self.cost_guard = CostGuard(0)
        self.stop_escalation = StopEscalationJudge()
        self.production_monitor = ProductionMonitor()
        self.recovery_supervisor = RecoverySupervisor(escalation=self.stop_escalation)
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
                "ios_simulator_native_build": True,
                "ios_signed_ipa": False,
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
                "specialist_execution_council": True,
                "verified_evolution_engine": True,
                "evolution_experiment_history": True,
                "release_manager": True,
                "observable_build_jobs": True,
                "reviewed_tool_executor": True,
                "project_health_check": True,
                "agent_safe_tool_execution": True,
                "agent_evidence_review": True,
                "agent_safe_execution": True,
                "evidence_backed_knowledge_promotion": True,
                "development_certificate": True,
                "recovery_supervisor": True,
                "independent_recovery_review": True,
                "validated_recovery_learning": True,
                "knowledge_factory": True,
                "resumable_knowledge_imports": True,
                "local_semantic_knowledge_search": True,
                "knowledge_confidence_feedback": True,
                "secrets_guard": True,
                "cost_guard": True,
                "stop_escalation_judge": True,
                "production_monitor": True,
            },
        }

    def operational_safety(self, project_slug: str | None = None) -> dict[str, Any]:
        settings_path = self.ai_engine.settings_path
        raw_settings: dict[str, Any] = {}
        if settings_path.is_file():
            try:
                loaded = json.loads(settings_path.read_text(encoding="utf-8"))
                raw_settings = loaded if isinstance(loaded, dict) else {}
            except Exception:
                raw_settings = {}
        settings_audit = self.secrets_guard.audit_settings(raw_settings)
        project_audit = None
        slug = str(project_slug or "").strip()
        if slug:
            project_dir = safe_child(WORKSPACE_DIR, slug)
            if not project_dir.is_dir():
                raise FileNotFoundError(slug)
            project_audit = self.secrets_guard.audit_project(project_dir).to_dict()
        return {
            "secrets": {
                "settings": settings_audit.to_dict(),
                "project": project_audit,
                "rule": "secret values are never returned by this audit",
            },
            "cost": {
                "session": self.cost_guard.snapshot(),
                "rule": "metered or unknown-cost operations require explicit approval and a configured budget",
            },
            "autonomy": {
                "max_repair_attempts": self.stop_escalation.MAX_REPAIR_ATTEMPTS,
                "red_risk_requires_human": True,
                "repeated_failure_stops": True,
                "missing_permissions_escalate": True,
            },
        }

    def configure_cost_budget(self, budget_yen: int | float | str, *, approved: bool) -> dict[str, str]:
        if not approved:
            raise PermissionError("explicit approval is required before enabling a paid-operation budget")
        self.cost_guard = CostGuard(budget_yen)
        return self.cost_guard.snapshot()

    def check_cost_operation(
        self,
        *,
        billing_mode: str,
        estimated_cost_yen: int | float | str | None = None,
        approved: bool = False,
        commit: bool = False,
    ) -> dict[str, Any]:
        decision = self.cost_guard.check(
            billing_mode=billing_mode,
            estimated_cost_yen=estimated_cost_yen,
            explicitly_approved=approved,
        )
        payload = decision.to_dict()
        if commit:
            if not approved:
                raise PermissionError("explicit approval is required before committing paid cost")
            payload["committed_total_yen"] = self.cost_guard.commit(decision)
            payload["session"] = self.cost_guard.snapshot()
        return payload

    def evaluate_production_health(
        self,
        project_slug: str,
        samples: list[dict[str, Any]],
    ) -> dict[str, Any]:
        slug = project_slug.strip()
        if not slug:
            raise ValueError("project_slug is required")
        project_dir = safe_child(WORKSPACE_DIR, slug)
        if not project_dir.is_dir():
            raise FileNotFoundError(slug)
        parsed = []
        for row in samples:
            if not isinstance(row, dict):
                raise ValueError("health samples must be objects")
            parsed.append(HealthSample(
                ok=bool(row.get("ok")),
                status_code=row.get("status_code"),
                latency_ms=row.get("latency_ms"),
                error=str(row.get("error") or ""),
                observed_at=str(row.get("observed_at") or ""),
            ))
        report = self.production_monitor.evaluate(parsed)
        path = self.production_monitor.save(project_dir, report)
        payload = report.to_dict()
        payload["report_path"] = path.relative_to(project_dir).as_posix()
        return payload

    def specialist_agents(self) -> list[dict[str, Any]]:
        return self.specialists.public_contract()

    def agent_tools(self) -> list[dict[str, Any]]:
        executable = set(self.tool_executor.executable_tools())
        rows = []
        for tool in self.tools.list():
            row = tool.to_dict()
            row["executable"] = tool.name in executable
            rows.append(row)
        return rows

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

    def create_evolution_experiment(
        self,
        *,
        title: str,
        baseline_label: str,
        candidate_label: str,
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
        item = self.evolution_experiments.create(
            title=title,
            baseline_label=baseline_label,
            candidate_label=candidate_label,
            changed_paths=changed_paths,
            evidence_refs=evidence_refs,
            decision=decision,
        )
        return item.to_dict()

    def list_evolution_experiments(self) -> list[dict[str, Any]]:
        return [x.to_dict() for x in self.evolution_experiments.list()]

    def review_evolution_experiment(
        self,
        experiment_id: str,
        *,
        approved: bool,
        note: str = "",
    ) -> dict[str, Any]:
        return self.evolution_experiments.record_human_review(
            experiment_id,
            approved=approved,
            note=note,
        ).to_dict()

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

    def run_agent_safe_tools(
        self,
        goal: str,
        *,
        project_slug: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        slug = str(project_slug or "").strip()
        if not slug:
            raise ValueError("project_slug is required for safe specialist execution")
        return self.run_specialist_execution_council(
            goal,
            slug,
            context=context or {},
        )

    def run_specialist_execution_council(
        self,
        goal: str,
        project_slug: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_goal = goal.strip()
        slug = project_slug.strip()
        if not clean_goal:
            raise ValueError("goal is required")
        if not slug:
            raise ValueError("project_slug is required")
        project_dir = safe_child(WORKSPACE_DIR, slug)
        if not project_dir.is_dir():
            raise FileNotFoundError(slug)
        combined = dict(context or {})
        combined["verified_agent_context"] = self.agent.context(clean_goal)
        combined["project_slug"] = slug
        report = self.execution_council.run(
            clean_goal,
            slug,
            context=combined,
        )
        history_path = self.execution_council.save(project_dir, report)
        payload = report.to_dict()
        payload["history_path"] = history_path.relative_to(project_dir).as_posix()
        return payload

    def agent_context(self, goal: str) -> dict[str, Any]:
        return self.agent.context(goal)

    def verified_knowledge(self, query: str = "") -> list[dict[str, Any]]:
        if not query.strip():
            return [x.to_dict() for x in self.knowledge.list("verified")]
        rows = self.knowledge_search.search(
            query,
            verified_only=True,
            limit=8,
            minimum_confidence=0.45,
        )
        return [row.item.to_dict() for row in rows]

    def search_knowledge(
        self,
        query: str,
        *,
        verified_only: bool = True,
        limit: int = 8,
        minimum_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:
        return [
            row.to_dict()
            for row in self.knowledge_search.search(
                query,
                verified_only=verified_only,
                limit=limit,
                minimum_confidence=minimum_confidence,
            )
        ]

    def ingest_knowledge_batch(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        return self.knowledge_factory.ingest_batch(rows).to_dict()

    def start_knowledge_import(self, name: str) -> dict[str, Any]:
        return self.knowledge_imports.start(name).to_dict()

    def ingest_knowledge_import_page(
        self,
        import_id: str,
        *,
        page_index: int,
        rows: list[dict[str, Any]],
        final: bool = False,
    ) -> dict[str, Any]:
        return self.knowledge_imports.ingest_page(
            import_id,
            page_index=page_index,
            rows=rows,
            final=final,
        ).to_dict()

    def knowledge_import(self, import_id: str) -> dict[str, Any]:
        return self.knowledge_imports.get(import_id).to_dict()

    def list_knowledge_imports(self, limit: int = 50) -> list[dict[str, Any]]:
        return [row.to_dict() for row in self.knowledge_imports.list(limit)]

    def record_knowledge_outcome(
        self,
        knowledge_ids: list[str],
        *,
        success: bool,
        project_slug: str,
        evidence_ref: str,
    ) -> list[dict[str, Any]]:
        return [
            row.to_dict()
            for row in self.knowledge_search.record_outcome(
                knowledge_ids,
                success=success,
                project_slug=project_slug,
                evidence_ref=evidence_ref,
            )
        ]

    def staged_knowledge(self, trust_level: str | None = None) -> list[dict[str, Any]]:
        return [x.to_dict() for x in self.knowledge.list(trust_level)]

    def promote_knowledge_candidate(self, knowledge_id: str) -> dict[str, Any]:
        return self.knowledge.promote_candidate(knowledge_id).to_dict()

    def verify_knowledge_from_project(
        self,
        knowledge_id: str,
        *,
        project_slug: str,
        verifier_types: list[str],
    ) -> dict[str, Any]:
        return self.knowledge_verifier.verify(
            knowledge_id,
            project_slug=project_slug,
            verifier_types=verifier_types,
        ).to_dict()

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
        detail = self.catalog.detail(slug)
        project_dir = safe_child(WORKSPACE_DIR, slug)
        detail["certificate_integrity"] = self.development_certificates.verify_saved(
            project_dir
        ).to_dict()
        return detail

    def project_health(self, slug: str) -> dict[str, Any]:
        report = self.project_health_checker.run(slug)
        return report.to_dict()

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

    def run_safe_agent(
        self,
        goal: str,
        project_slug: str,
    ) -> dict[str, Any]:
        clean_goal = goal.strip()
        slug = project_slug.strip()
        if not clean_goal:
            raise ValueError("goal is required")
        if not slug:
            raise ValueError("project_slug is required")
        project_dir = safe_child(WORKSPACE_DIR, slug)
        if not project_dir.is_dir():
            raise FileNotFoundError(slug)
        plan = self.agent.plan(clean_goal, slug)
        report = self.agent_plan_runner.run(
            plan,
            project_dir=project_dir,
        )
        return report.to_dict()

    def start_build_job(
        self,
        slug: str,
        instruction: str,
        *,
        approved: bool,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        if not approved:
            raise PermissionError("explicit user approval is required before build job creation")
        clean = instruction.strip()
        if not clean:
            raise ValueError("instruction is required")
        project_dir = safe_child(WORKSPACE_DIR, slug)
        if not project_dir.is_dir():
            raise FileNotFoundError(slug)

        job = self.build_jobs.submit(
            slug,
            lambda progress: self.core_result_dict(
                self.build_project(
                    slug,
                    clean,
                    approved=True,
                    progress=progress,
                    thread_id=thread_id,
                )
            ),
        )
        return job.to_dict()

    def build_job(self, job_id: str) -> dict[str, Any]:
        return self.build_jobs.get(job_id).to_dict()

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
        baseline_evaluation = self.recovery_supervisor.capture(project_dir)

        def emit_platform(stage: str, message: str) -> None:
            if progress is None:
                return
            try:
                progress(stage, message)
            except Exception:
                pass

        def core_progress(stage: str, message: str) -> None:
            if stage == "done":
                emit_platform(
                    "core_checked",
                    "AICore内部確認が完了しました。独立Postflightへ進みます",
                )
                return
            emit_platform(stage, message)

        plan = self.agent.plan(instruction, slug)
        ledger = EvidenceLedger(project_dir)
        ledger.record(
            run_id=plan.run_id,
            stage="plan",
            status="ready",
            summary=f"{len(plan.steps)} bounded agent steps prepared",
            source="agent-orchestrator",
        )

        emit_platform(
            "preflight",
            "既存状態とVerified Knowledgeを安全に確認しています",
        )
        preflight = self.agent_plan_runner.run_preflight(
            plan,
            project_dir=project_dir,
        )
        ledger.record(
            run_id=plan.run_id,
            stage="inspect",
            status="pass",
            summary="project inspection and Verified Knowledge preflight completed",
            source="agent-plan-runner",
        )

        preparation = next(row.result for row in preflight.steps if row.tool_name == 'change.prepare')
        checkpoint = preparation['checkpoint']
        knowledge_step = next(
            (row.result for row in preflight.steps if row.tool_name == "knowledge.search"),
            None,
        ) or {}
        used_knowledge_ids = [
            str(item.get("knowledge_id") or "")
            for item in (knowledge_step.get("knowledge") or [])
            if isinstance(item, dict) and str(item.get("knowledge_id") or "").strip()
        ]

        def recover_failed_change() -> dict[str, Any]:
            recovery = CheckpointManager().restore(project_dir, checkpoint['checkpoint_id'], checkpoint['manifest_sha256'])
            ledger.record(run_id=plan.run_id, stage='repair', status='recovered',
                          summary='Verified pre-change source recovered to ' + recovery['recovered_tree'],
                          source='checkpoint-manager')
            return recovery

        try:
            result = self.core.execute(
                project_name,
                slug,
                project_dir,
                instruction,
                core_progress,
            )
        except Exception:
            recover_failed_change()
            raise

        candidate_evaluation = self.recovery_supervisor.capture(project_dir)
        failure_classification = self.recovery_supervisor.classify(
            result.pipeline_report,
            result.repair_attempts,
        )
        recovery_decision = self.recovery_supervisor.decide(
            baseline_evaluation,
            candidate_evaluation,
            repair_attempts=result.repair_attempts,
            classification=failure_classification,
        )
        recovery_path = self.recovery_supervisor.save(
            project_dir,
            baseline=baseline_evaluation,
            candidate=candidate_evaluation,
            classification=failure_classification,
            decision=recovery_decision,
        )
        recovery_payload = {
            "classification": failure_classification.to_dict(),
            "decision": recovery_decision.to_dict(),
            "report_path": recovery_path.relative_to(project_dir).as_posix(),
        }
        current_pipeline = dict(result.pipeline_report or {})
        current_pipeline["recovery_supervision"] = recovery_payload
        result.pipeline_report = current_pipeline
        ledger.record(
            run_id=plan.run_id,
            stage="repair",
            status=recovery_decision.action,
            summary=(
                f"recovery supervisor: {failure_classification.kind} / "
                f"{recovery_decision.action} / {recovery_decision.reason}"
            ),
            source="recovery-supervisor",
        )
        if result.ok and recovery_decision.action != "accept":
            result.ok = False
            result.message = (
                "自動修正後の独立比較で安全な改善を確認できなかったため、"
                f"完成扱いを停止しました。判断: {recovery_decision.action}"
            )

        emit_platform(
            "postflight",
            "別経路のTool ExecutorでTests・Design・Securityを再検証しています",
        )
        preflight_pipeline = dict(result.pipeline_report or {})
        preflight_pipeline["agent_preflight"] = preflight.to_dict()
        result.pipeline_report = preflight_pipeline

        postflight = self.project_health_checker.run(
            slug,
            run_id=plan.run_id,
        )
        postflight_path = self.project_health_checker.save(
            project_dir,
            postflight,
        )
        postflight_pipeline = dict(result.pipeline_report or {})
        postflight_pipeline["agent_postflight"] = postflight.to_dict()
        postflight_pipeline["agent_postflight_path"] = postflight_path.relative_to(project_dir).as_posix()
        result.pipeline_report = postflight_pipeline
        if result.ok and postflight.status != "pass":
            result.ok = False
            result.message = (
                "AICore完了後の独立PostflightでTests / Design / Securityの"
                "再検証に失敗したため、完成扱いを停止しました。"
            )

        independent_review = self.recovery_supervisor.independent_review(
            baseline_evaluation,
            candidate_evaluation,
            recovery_decision,
            postflight_ok=postflight.status == "pass",
        )
        self.recovery_supervisor.save(
            project_dir,
            baseline=baseline_evaluation,
            candidate=candidate_evaluation,
            classification=failure_classification,
            decision=recovery_decision,
            review=independent_review,
        )
        review_pipeline = dict(result.pipeline_report or {})
        review_pipeline["independent_recovery_review"] = independent_review.to_dict()
        result.pipeline_report = review_pipeline
        ledger.record(
            run_id=plan.run_id,
            stage="review",
            status="pass" if independent_review.approved else "blocked",
            summary=(
                "independent deterministic recovery review approved"
                if independent_review.approved
                else "independent recovery review requires changes: "
                + ", ".join(independent_review.findings)
            ),
            source="recovery-supervisor",
        )
        if result.ok and not independent_review.approved:
            result.ok = False
            result.message = (
                "独立Reviewerが品質・回帰・修正回数の条件を満たしていないと判断したため、"
                "完成扱いを停止しました。"
            )

        emit_platform(
            "trace",
            "実行結果とAgent PlanのEvidenceを照合しています",
        )
        trace = self.build_execution_tracer.create(plan, result, project_dir)
        pipeline_report = dict(result.pipeline_report or {})
        pipeline_report["agent_execution_trace"] = trace.to_dict()
        result.pipeline_report = pipeline_report

        trace_verified = trace.status == "verified"
        validated = bool(result.ok and trace_verified)
        if not validated:
            result.pipeline_report['checkpoint_recovery'] = recover_failed_change()
        if result.ok and not trace_verified:
            result.ok = False
            result.message = (
                "AICoreの生成結果とAgent Execution TraceのEvidenceが一致しないため、"
                "完成扱いを停止しました。"
            )

        ledger.record(
            run_id=plan.run_id,
            stage="validate",
            status="pass" if validated else "blocked",
            summary=result.message,
            source="agent-execution-trace",
        )
        if validated:
            ledger.record(
                run_id=plan.run_id,
                stage="review",
                status="approval_required",
                summary="external publish/signing/store submission still requires explicit human approval",
                source="agent-execution-trace",
            )
            ledger.record(
                run_id=plan.run_id,
                stage="report",
                status="verified",
                summary="generation completed with execution trace and platform quality gates satisfied",
                source="agent-execution-trace",
            )

        run_evidence = [
            row for row in ledger.recent(300)
            if row.run_id == plan.run_id
        ]
        completion = self.agent.completion_check(run_evidence)
        pipeline_report = dict(result.pipeline_report or {})
        pipeline_report["agent_completion"] = completion
        result.pipeline_report = pipeline_report
        if result.ok and not completion.get("complete"):
            result.ok = False
            missing = ", ".join(completion.get("missing_evidence") or []) or "unknown"
            result.message = (
                "Agent completion Evidenceが不足しているため完成扱いを停止しました。"
                f" 不足: {missing}"
            )

        emit_platform(
            "certificate",
            "Preflight・Postflight・成果物hashからDevelopment Certificateを作成しています",
        )
        certificate = self.development_certificates.create(
            project_dir,
            run_id=plan.run_id,
            project_slug=slug,
            execution_trace_path=trace.history_path,
            agent_completion=completion,
            preflight_path=preflight.history_path,
            postflight_path=postflight_path.relative_to(project_dir).as_posix(),
        )
        certificate_path = self.development_certificates.save(project_dir, certificate)
        result_files = getattr(result, "files", None)
        if isinstance(result_files, list):
            result_files.append(certificate_path)
        pipeline_report = dict(result.pipeline_report or {})
        pipeline_report["development_certificate"] = certificate.to_dict()
        result.pipeline_report = pipeline_report
        if result.ok and not certificate.preview_verified:
            result.ok = False
            result.message = (
                "Development Certificateの独立Evidenceが不足しているため、"
                "完成扱いを停止しました。"
            )

        learning = self.recovery_supervisor.learning_decision(
            classification=failure_classification,
            decision=recovery_decision,
            review=independent_review,
            certificate_verified=certificate.preview_verified,
            evidence_refs=[
                certificate_path.relative_to(project_dir).as_posix(),
                postflight_path.relative_to(project_dir).as_posix(),
                str(trace.history_path or ""),
            ],
        )
        if learning.promote:
            self.agent.memory.record(
                category="verified_recovery",
                input_text=instruction,
                lesson=learning.lesson,
                outcome="verified",
                project_slug=slug,
                verified=True,
                evidence_source=certificate_path.relative_to(project_dir).as_posix(),
            )
            ledger.record(
                run_id=plan.run_id,
                stage="report",
                status="learned",
                summary=learning.lesson,
                source="validated-recovery-learning",
            )
        final_recovery_path = self.recovery_supervisor.save(
            project_dir,
            baseline=baseline_evaluation,
            candidate=candidate_evaluation,
            classification=failure_classification,
            decision=recovery_decision,
            review=independent_review,
            learning=learning,
        )
        learning_pipeline = dict(result.pipeline_report or {})
        learning_pipeline["validated_recovery_learning"] = learning.to_dict()
        learning_pipeline["recovery_supervision_report"] = final_recovery_path.relative_to(project_dir).as_posix()
        result.pipeline_report = learning_pipeline

        knowledge_feedback = self.record_knowledge_outcome(
            used_knowledge_ids,
            success=bool(result.ok),
            project_slug=slug,
            evidence_ref=certificate_path.relative_to(project_dir).as_posix(),
        ) if used_knowledge_ids else []
        final_pipeline = dict(result.pipeline_report or {})
        final_pipeline["knowledge_feedback"] = {
            "knowledge_ids": used_knowledge_ids,
            "success": bool(result.ok),
            "usage": knowledge_feedback,
        }
        result.pipeline_report = final_pipeline

        emit_platform(
            "done" if result.ok else "issue",
            "全Evidenceの確認が完了しました" if result.ok else "確認が必要なEvidenceがあります",
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
            "ios_source_build": result.ios_source_build,
            "ios_simulator_build": result.ios_simulator_build,
            "release_report": result.release_report,
        }

    def delivery_options(self, slug: str) -> list[dict[str, Any]]:
        return [asdict(x) for x in self.catalog.delivery_options(slug)]
