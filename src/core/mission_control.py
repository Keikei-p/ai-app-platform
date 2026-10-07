from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
import json
import uuid

from .config import DATA_DIR
from .redaction import redact_sensitive


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Mission:
    mission_id: str
    project_slug: str
    goal: str
    status: str
    phase: str
    created_at: str
    updated_at: str
    cycle: int = 0
    max_cycles: int = 8
    requires_approval: bool = False
    message: str = ""
    plan: dict[str, Any] = field(default_factory=dict)
    build_job_id: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MissionStore:
    """Persistent lifecycle state for long-horizon Aivy work."""

    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "aivy_missions.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        self._lock = RLock()
        self._recover_interrupted()

    def create(self, *, project_slug: str, goal: str, plan: dict[str, Any], max_cycles: int = 8) -> Mission:
        clean_goal = redact_sensitive(goal.strip())[:6000]
        clean_slug = redact_sensitive(project_slug.strip())[:180]
        if not clean_goal or not clean_slug:
            raise ValueError("project_slug and goal are required")
        now = _now()
        mission = Mission(
            mission_id=uuid.uuid4().hex,
            project_slug=clean_slug,
            goal=clean_goal,
            status="queued",
            phase="planned",
            created_at=now,
            updated_at=now,
            max_cycles=max(1, min(int(max_cycles), 32)),
            message="Mission is ready for preflight.",
            plan=dict(plan or {}),
            history=[{"at": now, "status": "queued", "phase": "planned", "message": "Mission created"}],
        )
        with self._lock:
            rows = self._read()
            rows[mission.mission_id] = mission
            self._write(rows)
        return mission

    def list(self, limit: int = 100) -> list[Mission]:
        rows = list(self._read().values())
        rows.sort(key=lambda x: x.updated_at, reverse=True)
        return rows[: max(1, min(int(limit), 500))]

    def get(self, mission_id: str) -> Mission:
        mission = self._read().get(str(mission_id).strip())
        if mission is None:
            raise KeyError(mission_id)
        return mission

    def update(
        self,
        mission_id: str,
        *,
        status: str | None = None,
        phase: str | None = None,
        message: str | None = None,
        cycle: int | None = None,
        requires_approval: bool | None = None,
        build_job_id: str | None | object = ...,
        evidence_refs: list[str] | None = None,
        result: dict[str, Any] | None | object = ...,
    ) -> Mission:
        with self._lock:
            rows = self._read()
            mission = rows.get(str(mission_id).strip())
            if mission is None:
                raise KeyError(mission_id)
            if mission.status in TERMINAL_STATUSES and status not in {None, mission.status}:
                raise ValueError("terminal mission cannot transition")

            if status is not None:
                mission.status = str(status)[:80]
            if phase is not None:
                mission.phase = str(phase)[:120]
            if message is not None:
                mission.message = redact_sensitive(str(message))[:2000]
            if cycle is not None:
                mission.cycle = max(0, int(cycle))
            if requires_approval is not None:
                mission.requires_approval = bool(requires_approval)
            if build_job_id is not ...:
                mission.build_job_id = str(build_job_id).strip()[:180] if build_job_id else None
            if evidence_refs is not None:
                mission.evidence_refs = list(dict.fromkeys(
                    redact_sensitive(str(x).strip())[:500]
                    for x in evidence_refs if str(x).strip()
                ))[:100]
            if result is not ...:
                mission.result = dict(result) if isinstance(result, dict) else None

            mission.updated_at = _now()
            mission.history.append({
                "at": mission.updated_at,
                "status": mission.status,
                "phase": mission.phase,
                "message": mission.message,
            })
            mission.history = mission.history[-200:]
            rows[mission.mission_id] = mission
            self._write(rows)
            return mission

    def pause(self, mission_id: str) -> Mission:
        mission = self.get(mission_id)
        if mission.status in TERMINAL_STATUSES:
            return mission
        if mission.build_job_id and mission.status == "running":
            raise RuntimeError("active build must reach a safe boundary before pause")
        return self.update(
            mission_id,
            status="paused",
            phase="paused",
            message="Mission paused with state preserved.",
            requires_approval=False,
        )

    def cancel(self, mission_id: str) -> Mission:
        mission = self.get(mission_id)
        if mission.status in TERMINAL_STATUSES:
            return mission
        if mission.build_job_id and mission.status == "running":
            raise RuntimeError("active build must reach a safe boundary before cancel")
        return self.update(
            mission_id,
            status="cancelled",
            phase="cancelled",
            message="Mission ended without deleting project data.",
            requires_approval=False,
        )

    def _recover_interrupted(self) -> None:
        with self._lock:
            rows = self._read()
            changed = False
            for mission in rows.values():
                if mission.status == "running":
                    interrupted_build = bool(mission.build_job_id)
                    mission.status = "paused"
                    mission.phase = "resume_required"
                    mission.requires_approval = False
                    # BuildJobManager workers are process-local. After a host
                    # restart the old job id cannot be trusted or resumed.
                    # Clear it so the mission can safely re-run preflight and
                    # stop at the normal build-approval boundary.
                    mission.build_job_id = None
                    mission.message = (
                        "Aivy restarted during an active build. Mission state and evidence were "
                        "preserved; preflight must be repeated before a new build approval."
                        if interrupted_build
                        else "Aivy restarted while this mission was active. State was preserved for safe resume."
                    )
                    mission.updated_at = _now()
                    mission.history.append({
                        "at": mission.updated_at,
                        "status": mission.status,
                        "phase": mission.phase,
                        "message": mission.message,
                    })
                    mission.history = mission.history[-200:]
                    changed = True
            if changed:
                self._write(rows)

    def _read(self) -> dict[str, Mission]:
        raw = self._read_payload(self.path)
        if raw is None:
            backup = self._read_payload(self.backup_path)
            if backup is None:
                return {}
            # Restore the last verified-readable snapshot without copying a
            # corrupt primary over the backup.
            self._write_payload_atomically(self.path, backup)
            raw = backup

        rows: dict[str, Mission] = {}
        for item in raw:
            try:
                mission = Mission(
                    mission_id=str(item["mission_id"]),
                    project_slug=str(item["project_slug"]),
                    goal=str(item["goal"]),
                    status=str(item["status"]),
                    phase=str(item["phase"]),
                    created_at=str(item["created_at"]),
                    updated_at=str(item["updated_at"]),
                    cycle=max(0, int(item.get("cycle") or 0)),
                    max_cycles=max(1, min(int(item.get("max_cycles") or 8), 32)),
                    requires_approval=bool(item.get("requires_approval")),
                    message=str(item.get("message") or ""),
                    plan=dict(item.get("plan") or {}),
                    build_job_id=str(item.get("build_job_id") or "") or None,
                    evidence_refs=[str(x) for x in item.get("evidence_refs") or ()],
                    history=[dict(x) for x in item.get("history") or () if isinstance(x, dict)],
                    result=dict(item["result"]) if isinstance(item.get("result"), dict) else None,
                )
                rows[mission.mission_id] = mission
            except Exception:
                continue
        return rows

    @staticmethod
    def _read_payload(path: Path) -> list[Any] | None:
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return raw if isinstance(raw, list) else None

    @staticmethod
    def _write_payload_atomically(path: Path, payload: list[dict[str, Any]]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)

    def _write(self, rows: dict[str, Mission]) -> None:
        current = self._read_payload(self.path)
        if current is not None:
            self._write_payload_atomically(self.backup_path, current)
        payload = [x.to_dict() for x in rows.values()]
        self._write_payload_atomically(self.path, payload)
