from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable
import uuid


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
    """Single-worker local build queue for observable Aivy generation progress.

    It does not grant build permission. The caller must enforce explicit approval
    before submitting a job. One worker prevents concurrent writes to generated
    project state from racing each other.
    """

    def __init__(self, max_history: int = 50):
        self.max_history = max(5, min(int(max_history), 200))
        self._jobs: dict[str, BuildJob] = {}
        self._lock = Lock()
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
            self._jobs[job.job_id] = job
            self._prune_locked()
        self._executor.submit(self._run, job.job_id, runner)
        return self.get(job.job_id)

    def get(self, job_id: str) -> BuildJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return BuildJob(**job.to_dict())

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

    def _prune_locked(self) -> None:
        if len(self._jobs) <= self.max_history:
            return
        done = [
            x for x in self._jobs.values()
            if x.status in {"completed", "blocked", "failed"}
        ]
        done.sort(key=lambda x: x.updated_at)
        for job in done[: max(0, len(self._jobs) - self.max_history)]:
            self._jobs.pop(job.job_id, None)
