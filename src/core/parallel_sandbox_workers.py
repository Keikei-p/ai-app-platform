from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import shutil
import uuid

from .agent_budget import AgentBudget, AgentBudgetTracker
from .config import STATE_DIR
from .llm_chat import AIChatEngine
from .model_router import ModelRouter
from .redaction import redact_sensitive
from .specialist_agents import SpecialistAgentRegistry
from .specialist_runtime import SpecialistRuntime


DEFAULT_PARALLEL_ROLES = ("research", "architect", "coding", "test", "design", "security")
BLOCKED_PARTS = {
    ".git", ".aiapp", ".vault", ".snapshots", "node_modules",
    "__pycache__", "artifacts",
}
BLOCKED_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3"}
TEXT_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".html", ".css",
    ".json", ".md", ".txt", ".yml", ".yaml", ".toml", ".ini", ".webmanifest",
}


@dataclass(frozen=True)
class SandboxWorkerResult:
    role: str
    status: str
    snapshot_path: str
    file_count: int
    total_bytes: int
    manifest_sha256: str
    specialist: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParallelSandboxReport:
    run_id: str
    goal: str
    project_slug: str
    status: str
    workers: tuple[SandboxWorkerResult, ...]
    source_manifest_before: str
    source_manifest_after: str
    source_unchanged: bool
    execution_mode: str
    summary: str
    history_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["workers"] = [x.to_dict() for x in self.workers]
        return data


class ParallelSandboxWorkerPool:
    """Parallel specialist analysis over isolated filesystem snapshots.

    Workers never receive write access to the source project. Each role gets its
    own copied snapshot and an independent model-call budget. The original
    project is fingerprinted before and after the parallel run so accidental
    source mutation is detectable.
    """

    MAX_WORKERS = 6
    MAX_SNAPSHOT_BYTES = 30 * 1024 * 1024
    MAX_FILE_BYTES = 2 * 1024 * 1024
    MAX_CONTEXT_CHARS = 36_000

    def __init__(
        self,
        *,
        engine: AIChatEngine | None = None,
        specialists: SpecialistAgentRegistry | None = None,
        router: ModelRouter | None = None,
        sandbox_root: Path | None = None,
    ):
        self.engine = engine or AIChatEngine()
        self.specialists = specialists or SpecialistAgentRegistry()
        self.router = router or ModelRouter(self.engine)
        self.sandbox_root = sandbox_root or (STATE_DIR / "sandboxes")
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        *,
        goal: str,
        project_slug: str,
        project_dir: Path,
        roles: tuple[str, ...] | None = None,
    ) -> ParallelSandboxReport:
        clean_goal = goal.strip()
        slug = project_slug.strip()
        root = Path(project_dir).resolve()
        if not clean_goal or not slug:
            raise ValueError("goal and project_slug are required")
        if not root.is_dir():
            raise FileNotFoundError(slug)

        selected = tuple(roles or DEFAULT_PARALLEL_ROLES)
        if not selected or len(selected) > self.MAX_WORKERS:
            raise ValueError("invalid parallel worker count")
        if len(set(selected)) != len(selected):
            raise ValueError("parallel worker roles must be unique")
        for role in selected:
            self.specialists.get(role)

        run_id = "sandbox-" + uuid.uuid4().hex
        run_root = self.sandbox_root / run_id
        run_root.mkdir(parents=True, exist_ok=False)

        before = self._project_manifest(root)
        workers: list[SandboxWorkerResult] = []
        status = "completed"
        try:
            with ThreadPoolExecutor(
                max_workers=min(len(selected), self.MAX_WORKERS),
                thread_name_prefix="aivy-sandbox",
            ) as pool:
                futures = {
                    pool.submit(self._run_worker, run_root, role, clean_goal, slug, root): role
                    for role in selected
                }
                for future in as_completed(futures):
                    role = futures[future]
                    try:
                        workers.append(future.result())
                    except Exception as exc:
                        status = "partial"
                        workers.append(SandboxWorkerResult(
                            role=role,
                            status="error",
                            snapshot_path="",
                            file_count=0,
                            total_bytes=0,
                            manifest_sha256="",
                            specialist={
                                "specialist": role,
                                "status": "error",
                                "summary": f"{type(exc).__name__}: {redact_sensitive(str(exc))[:1000]}",
                                "findings": [],
                                "recommendations": [],
                                "requested_tools": [],
                                "uncertainties": [],
                                "route": {},
                            },
                        ))

            workers.sort(key=lambda x: selected.index(x.role))
            after = self._project_manifest(root)
            unchanged = before == after
            if not unchanged:
                status = "blocked"
            if all(x.specialist.get("status") == "not_connected" for x in workers):
                status = "not_connected"

            summary = (
                f"{len(workers)} isolated specialists completed in parallel; "
                f"source project unchanged={unchanged}."
            )
            report = ParallelSandboxReport(
                run_id=run_id,
                goal=clean_goal,
                project_slug=slug,
                status=status,
                workers=tuple(workers),
                source_manifest_before=before,
                source_manifest_after=after,
                source_unchanged=unchanged,
                execution_mode="parallel_isolated_readonly_snapshots",
                summary=summary,
            )
            history = self.save(root, report)
            return ParallelSandboxReport(
                **{**report.to_dict(), "workers": tuple(workers), "history_path": history.relative_to(root).as_posix()}
            )
        finally:
            shutil.rmtree(run_root, ignore_errors=True)

    def _run_worker(
        self,
        run_root: Path,
        role: str,
        goal: str,
        project_slug: str,
        source_root: Path,
    ) -> SandboxWorkerResult:
        snapshot = run_root / role
        manifest, total_bytes = self._copy_snapshot(source_root, snapshot)
        context = self._snapshot_context(snapshot, manifest)

        budget = AgentBudgetTracker(AgentBudget(
            max_model_calls=1,
            max_research_sources=0,
            max_tool_calls=0,
            max_repair_attempts=0,
            max_specialist_output_chars=8_000,
        ))
        runtime = SpecialistRuntime(
            engine=self.engine,
            registry=self.specialists,
            router=self.router,
            budget=budget,
        )
        task = (
            f"Analyze this isolated snapshot for the goal: {goal}. "
            "Do not assume access to the live project. Do not execute tools or modify files. "
            "Return findings and recommendations for the coordinator."
        )
        result = runtime.consult(
            role,
            task,
            {
                "goal": goal,
                "project_slug": project_slug,
                "sandbox": {
                    "role": role,
                    "isolated": True,
                    "write_access_to_source": False,
                    "shell_access": False,
                    "network_access": False,
                },
                "snapshot": context,
            },
        )
        return SandboxWorkerResult(
            role=role,
            status="completed" if result.status == "ok" else result.status,
            snapshot_path=snapshot.name,
            file_count=len(manifest),
            total_bytes=total_bytes,
            manifest_sha256=self._manifest_hash(manifest),
            specialist=result.to_dict(),
        )

    def _copy_snapshot(self, source: Path, target: Path) -> tuple[list[dict[str, Any]], int]:
        target.mkdir(parents=True, exist_ok=False)
        manifest: list[dict[str, Any]] = []
        total = 0
        for path in sorted(source.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(source)
            if any(part in BLOCKED_PARTS for part in rel.parts):
                continue
            if path.name.startswith(".env") or path.suffix.lower() in BLOCKED_SUFFIXES:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > self.MAX_FILE_BYTES:
                continue
            if total + size > self.MAX_SNAPSHOT_BYTES:
                break
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)
            raw = dst.read_bytes()
            total += len(raw)
            manifest.append({
                "path": rel.as_posix(),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
        return manifest, total

    def _snapshot_context(self, snapshot: Path, manifest: list[dict[str, Any]]) -> dict[str, Any]:
        snippets: list[dict[str, str]] = []
        used = 0
        for row in manifest:
            path = snapshot / row["path"]
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            room = self.MAX_CONTEXT_CHARS - used
            if room <= 0:
                break
            piece = text[: min(room, 6000)]
            snippets.append({"path": row["path"], "content": piece})
            used += len(piece)
        return {
            "manifest": manifest[:300],
            "snippets": snippets,
            "manifest_sha256": self._manifest_hash(manifest),
        }

    def _project_manifest(self, root: Path) -> str:
        rows: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root)
            if any(part in BLOCKED_PARTS for part in rel.parts):
                continue
            if path.name.startswith(".env") or path.suffix.lower() in BLOCKED_SUFFIXES:
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            rows.append({
                "path": rel.as_posix(),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
        return self._manifest_hash(rows)

    @staticmethod
    def _manifest_hash(rows: list[dict[str, Any]]) -> str:
        raw = json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def save(project_dir: Path, report: ParallelSandboxReport) -> Path:
        root = Path(project_dir)
        target = root / ".aiapp" / "agent" / "parallel" / f"{report.run_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": report.run_id,
            "goal": redact_sensitive(report.goal)[:3000],
            "project_slug": report.project_slug,
            "status": report.status,
            "execution_mode": report.execution_mode,
            "summary": redact_sensitive(report.summary)[:2000],
            "source_unchanged": report.source_unchanged,
            "source_manifest_before": report.source_manifest_before,
            "source_manifest_after": report.source_manifest_after,
            "workers": [
                {
                    "role": worker.role,
                    "status": worker.status,
                    "file_count": worker.file_count,
                    "total_bytes": worker.total_bytes,
                    "manifest_sha256": worker.manifest_sha256,
                    "specialist": {
                        "status": worker.specialist.get("status"),
                        "summary": redact_sensitive(str(worker.specialist.get("summary") or ""))[:2000],
                        "findings": [
                            redact_sensitive(str(x))[:1600]
                            for x in worker.specialist.get("findings") or []
                        ],
                        "recommendations": [
                            redact_sensitive(str(x))[:1600]
                            for x in worker.specialist.get("recommendations") or []
                        ],
                        "uncertainties": [
                            redact_sensitive(str(x))[:1600]
                            for x in worker.specialist.get("uncertainties") or []
                        ],
                        "route": dict(worker.specialist.get("route") or {}),
                    },
                }
                for worker in report.workers
            ],
        }
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
        return target
