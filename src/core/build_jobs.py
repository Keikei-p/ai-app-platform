from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable
import json
import uuid

from .redaction import redact_sensitive


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BuildJob:
    job_id: str
    project_slug: str
    status: str
    stage: str
    message: str
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "project_slug": self.project_slug,
            "status": self.status,
            "stage": self.stage,
            "message": self.message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": self.result,
            "error": self.error,
        }


class BuildJobManager:
    """Single-worker, approval-gated queue with optional restart-safe audit.

    A persisted job is an observation, never a command to execute work. On
    restart queued/running jobs become terminal 'failed'/'interrupted' records.
    A new build always requires the caller's ordinary preflight and approval.
    Raw build results, exception text, and arbitrary model output are never
    persisted; only sanitized, bounded status metadata is stored.
    """

    _TERMINAL = {"completed", "blocked", "failed"}

    def __init__(
        self,
        max_history: int = 50,
        *,
        history_path: Path | None = None,
        stall_seconds: int = 30 * 60,
    ):
        self.max_history = max(5, min(int(max_history), 200))
        self._jobs: dict[str, BuildJob] = {}
        self._lock = Lock()
        self.history_path = Path(history_path) if history_path is not None else None
        self.backup_path = (
            self.history_path.with_suffix(self.history_path.suffix + ".bak")
            if self.history_path is not None else None
        )
        self.stall_seconds = max(60, int(stall_seconds))
        self._persistence_issue: str | None = None
        if self.history_path is not None:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_history()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aivy-build")

    def submit(
        self,
        project_slug: str,
        runner: Callable[[Callable[[str, str], None]], dict[str, Any]],
    ) -> BuildJob:
        job = BuildJob(
            job_id=uuid.uuid4().hex,
            project_slug=project_slug,
            status="queued",
            stage="queued",
            message="Aivy build is queued",
            created_at=_now(),
            updated_at=_now(),
        )
        with self._lock:
            if self._persistence_issue:
                raise RuntimeError(
                    "Build history requires recovery before another build can start."
                )
            self._jobs[job.job_id] = job
            try:
                self._persist_locked()
            except Exception:
                self._jobs.pop(job.job_id, None)
                raise
            self._prune_locked()
        self._executor.submit(self._run, job.job_id, runner)
        return self.get(job.job_id)

    def get(self, job_id: str) -> BuildJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return BuildJob(**job.to_dict())

    def watchdog_status(self) -> dict[str, Any]:
        """Observe stalled builds without killing, retrying or approving them."""
        now = datetime.now(timezone.utc)
        with self._lock:
            active = [j for j in self._jobs.values() if j.status in {"queued", "running"}]
            stalled = []
            for job in active:
                try:
                    updated = datetime.fromisoformat(job.updated_at.replace("Z", "+00:00"))
                    if updated.tzinfo is None:
                        updated = updated.replace(tzinfo=timezone.utc)
                    age = (now - updated).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    age = self.stall_seconds + 1
                if age >= self.stall_seconds:
                    stalled.append(job.job_id)
            return {
                "active_count": len(active),
                "stalled_job_ids": stalled,
                "interrupted_count": sum(
                    1 for j in self._jobs.values()
                    if j.status == "failed" and j.stage == "interrupted"
                ),
                "persistence_ok": self._persistence_issue is None,
                "persistence_issue": self._persistence_issue,
                "watchdog_actions": "observation_only_no_auto_retry",
            }

    def _run(
        self,
        job_id: str,
        runner: Callable[[Callable[[str, str], None]], dict[str, Any]],
    ) -> None:
        self._update(job_id, status="running", stage="starting", message="Aivy build started")

        def progress(stage: str, message: str) -> None:
            self._update(job_id, status="running", stage=str(stage)[:80], message=str(message)[:1000])

        try:
            result = runner(progress)
            ok = bool(result.get("ok")) if isinstance(result, dict) else False
            self._update(
                job_id,
                status="completed" if ok else "blocked",
                stage="done" if ok else "issue",
                message=str((result or {}).get("message") or ("completed" if ok else "quality gate blocked"))[:1000],
                result=result if isinstance(result, dict) else None,
            )
        except Exception as exc:
            self._update(
                job_id,
                status="failed",
                stage="error",
                message="Aivy build failed safely",
                error=f"{type(exc).__name__}: {exc}"[:2000],
            )

    def _update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        stage: str | None = None,
        message: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if status is not None:
                job.status = status
            if stage is not None:
                job.stage = stage
            if message is not None:
                job.message = message
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error
            job.updated_at = _now()
            # Do not stop a running build halfway through a write if the audit
            # storage fails. Mark the issue, block *new* builds and surface it
            # through watchdog_status rather than pretending persistence worked.
            try:
                self._persist_locked()
            except (OSError, RuntimeError, ValueError):
                self._persistence_issue = "build_history_write_failed"

    def _prune_locked(self) -> None:
        if len(self._jobs) <= self.max_history:
            return
        done = [
            x for x in self._jobs.values()
            if x.status in self._TERMINAL
        ]
        done.sort(key=lambda x: x.updated_at)
        for job in done[: max(0, len(self._jobs) - self.max_history)]:
            self._jobs.pop(job.job_id, None)

    @staticmethod
    def _read_payload(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            return None
        jobs = raw.get("jobs")
        if not isinstance(jobs, list) or any(
            not isinstance(item, dict)
            or not all(isinstance(item.get(key), str) for key in (
                "job_id", "project_slug", "status", "stage", "message",
                "created_at", "updated_at",
            ))
            for item in jobs
        ):
            return None
        return raw

    @staticmethod
    def _atomic_write(path: Path, raw: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _load_history(self) -> None:
        assert self.history_path is not None
        assert self.backup_path is not None
        primary = self._read_payload(self.history_path)
        if primary is None:
            backup = self._read_payload(self.backup_path)
            if backup is not None:
                # Restore a verified-readable snapshot without rotating corrupt
                # primary data into its only known-good backup.
                self._atomic_write(self.history_path, backup)
                primary = backup
            elif self.history_path.exists() or self.backup_path.exists():
                self._persistence_issue = "build_history_unreadable"
                return
        if primary is None:
            return
        if self.backup_path.exists() and self._read_payload(self.backup_path) is None:
            self._persistence_issue = "build_history_backup_unreadable"
        interrupted = False
        for row in primary["jobs"]:
            try:
                restored = BuildJob(
                    job_id=row["job_id"],
                    project_slug=row["project_slug"],
                    status=row["status"],
                    stage=row["stage"],
                    message=row["message"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    result=row.get("result") if isinstance(row.get("result"), dict) else None,
                    error=None,
                )
                if restored.status in {"queued", "running"}:
                    restored.status = "failed"
                    restored.stage = "interrupted"
                    restored.message = (
                        "Aivy restarted before build completion; repeat preflight "
                        "and obtain new build approval."
                    )
                    restored.result = None
                    restored.updated_at = _now()
                    interrupted = True
                self._jobs[restored.job_id] = restored
            except (KeyError, ValueError, TypeError):
                self._persistence_issue = "build_history_unreadable"
                return
        self._prune_locked()
        if interrupted and self._persistence_issue is None:
            try:
                self._persist_locked()
            except (OSError, RuntimeError, ValueError):
                self._persistence_issue = "build_history_write_failed"

    def _persist_locked(self) -> None:
        if self.history_path is None:
            return
        assert self.backup_path is not None
        if self._persistence_issue:
            raise RuntimeError("Build history requires recovery.")
        current = self._read_payload(self.history_path)
        if current is None and (self.history_path.exists() or self.backup_path.exists()):
            raise RuntimeError("Build history is unreadable; refusing to overwrite.")
        if self.backup_path.exists() and self._read_payload(self.backup_path) is None:
            raise RuntimeError("Build history backup is unreadable; refusing to overwrite.")
        payload = {
            "schema_version": 1,
            "jobs": [
                {
                    "job_id": job.job_id,
                    "project_slug": redact_sensitive(str(job.project_slug))[:180],
                    "status": job.status,
                    "stage": redact_sensitive(str(job.stage))[:80],
                    "message": redact_sensitive(str(job.message))[:1000],
                    "created_at": job.created_at,
                    "updated_at": job.updated_at,
                    # Explicit allowlist: do not persist source code, project
                    # paths, arbitrary LLM output or raw exception details.
                    "result": {"ok": job.result.get("ok") is True}
                    if isinstance(job.result, dict) else None,
                }
                for job in self._jobs.values()
            ],
        }
        if current is not None:
            self._atomic_write(self.backup_path, current)
        self._atomic_write(self.history_path, payload)
