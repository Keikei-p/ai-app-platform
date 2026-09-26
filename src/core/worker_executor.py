from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .ai_core import AICore
from .backup import BackupManager
from .code_vault import CodeVault
from .config import VERSION, WORKSPACE_DIR
from .database import list_projects, log_event
from .environment import diagnose
from .maintenance import MaintenanceInspector
from .path_security import safe_child
from .project_manager import ProjectManager
from .test_runner import ProjectTestRunner


@dataclass(frozen=True)
class WorkerResult:
    ok: bool
    action: str
    data: dict


class WorkerExecutor:
    """Allowlisted local executor used by the Remote Worker.

    There is intentionally no generic shell, PowerShell, arbitrary executable, file delete,
    production deploy, billing, credential, or account-management action.
    """

    ALLOWED = {
        "status", "project_list", "project_create", "run_pipeline", "run_tests",
        "backup", "vault_save", "build_preview", "maintenance_scan", "create_snapshot",
    }
    MAX_INSTRUCTION_CHARS = 20_000
    MAX_PROJECT_NAME_CHARS = 120

    def __init__(self):
        self.pm = ProjectManager()
        self.tests = ProjectTestRunner()
        self.maintenance = MaintenanceInspector()
        self.core = AICore()
        self.backup = BackupManager()
        self.vault = CodeVault()

    def _project_dir(self, slug: str) -> Path:
        project_dir = safe_child(WORKSPACE_DIR, slug)
        if not project_dir.exists():
            raise FileNotFoundError(slug)
        return project_dir

    def execute(self, action: str, project_slug: str | None = None, payload: dict | None = None) -> WorkerResult:
        if action not in self.ALLOWED:
            return WorkerResult(False, action, {"error": "action_not_allowlisted"})
        payload = payload or {}

        if action == "status":
            # Do not expose detailed filesystem paths to a remote client.
            env = diagnose()
            safe_env = {k: env.get(k) for k in ("OS", "python", "git", "node", "npm") if k in env}
            return WorkerResult(True, action, {"version": VERSION, "environment": safe_env, "projects": len(list_projects())})

        if action == "project_list":
            projects = [{"name": str(p["name"]), "slug": str(p["slug"])} for p in list_projects()]
            return WorkerResult(True, action, {"projects": projects})

        if action == "project_create":
            name = str(payload.get("name") or "").strip()
            if not name or len(name) > self.MAX_PROJECT_NAME_CHARS:
                return WorkerResult(False, action, {"error": "invalid_project_name"})
            slug, _ = self.pm.create(name)
            log_event("worker.project_created", name, slug, "home-pc-worker")
            return WorkerResult(True, action, {"name": name, "slug": slug})

        if action == "backup":
            result = self.backup.create("remote")
            return WorkerResult(result.ok, action, {"created": result.ok, "error": result.error})

        if not project_slug:
            return WorkerResult(False, action, {"error": "project_required"})
        try:
            project_dir = self._project_dir(project_slug)
        except ValueError:
            return WorkerResult(False, action, {"error": "invalid_project_slug"})
        except FileNotFoundError:
            return WorkerResult(False, action, {"error": "project_not_found"})

        if action in {"run_tests", "test"}:
            rows = self.tests.run(project_dir)
            data = {"tests": [{"name": x.name, "passed": x.passed, "detail": x.detail} for x in rows]}
            log_event("worker.test", json.dumps(data, ensure_ascii=False), project_slug, "home-pc-worker")
            return WorkerResult(all(x.passed for x in rows), action, data)

        if action == "run_pipeline":
            instruction = str(payload.get("instruction") or "").strip()
            if not instruction or len(instruction) > self.MAX_INSTRUCTION_CHARS:
                return WorkerResult(False, action, {"error": "invalid_instruction"})
            try:
                meta = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
                name = str(meta.get("name") or project_slug)
            except (OSError, json.JSONDecodeError):
                name = project_slug
            result = self.core.execute(name, project_slug, project_dir, instruction)
            data = {
                "message": result.message,
                "tests": [{"name": t.name, "passed": t.passed, "detail": t.detail} for t in result.tests],
                "safety": {"allowed": result.safety.allowed, "level": result.safety.level, "reasons": result.safety.reasons},
            }
            return WorkerResult(result.ok, action, data)

        if action == "vault_save":
            version = self.vault.save(project_slug, "リモート保存", actor="home-pc-worker", reason="remote request", kind="remote")
            return WorkerResult(True, action, {"version_id": version.version_id, "file_count": version.file_count})

        if action == "maintenance_scan":
            findings = self.maintenance.inspect_project(project_dir)
            self.maintenance.record(project_slug, findings)
            return WorkerResult(True, action, {"findings": [x.__dict__ for x in findings]})

        if action == "create_snapshot":
            label = str(payload.get("label") or "remote-request")[:80]
            path = self.pm.snapshot(project_slug, label)
            return WorkerResult(True, action, {"created": True, "snapshot_name": path.name})

        if action == "build_preview":
            index = project_dir / "index.html"
            if not index.exists():
                return WorkerResult(False, action, {"error": "preview_not_generated"})
            return WorkerResult(True, action, {"available": True})

        return WorkerResult(False, action, {"error": "unhandled"})
