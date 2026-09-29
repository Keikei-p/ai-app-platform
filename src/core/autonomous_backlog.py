from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable
import hashlib
import json

from .config import DATA_DIR


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_day(value: str | None = None) -> str:
    if value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone().date().isoformat()
        except ValueError:
            pass
    return datetime.now().astimezone().date().isoformat()


@dataclass(frozen=True)
class BacklogItem:
    backlog_id: str
    source_key: str
    kind: str
    priority: int
    title: str
    reason: str
    target: str | None
    status: str
    requires_human_approval: bool
    evidence_refs: tuple[str, ...]
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        row = asdict(self)
        row["evidence_refs"] = list(self.evidence_refs)
        return row


class AutonomousBacklog:
    """Persistent daily view of what Aivy should do next.

    The backlog does not execute work. It mirrors the reviewed SelfDrive queue,
    approval boundaries and today's completed/failed actions into one durable,
    human-readable plan. This keeps autonomous prioritisation observable and
    prevents a second hidden execution path from bypassing SelfDrive safety.
    """

    def __init__(
        self,
        *,
        self_drive_status: Callable[[], dict[str, Any]],
        list_missions: Callable[[], list[dict[str, Any]]],
        path: Path | None = None,
    ):
        self.self_drive_status = self_drive_status
        self.list_missions = list_missions
        self.path = path or (DATA_DIR / "aivy_daily_backlog.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def refresh(self) -> dict[str, Any]:
        drive = self.self_drive_status()
        missions = self.list_missions()
        day = _local_day()
        now = _now()

        rows: dict[str, BacklogItem] = {}

        for action in drive.get("recent_actions") or []:
            if _local_day(str(action.get("created_at") or "")) != day:
                continue
            task = dict(action.get("task") or {})
            source_key = str(task.get("task_id") or "").strip()
            if not source_key:
                continue
            outcome = dict(action.get("outcome") or {})
            status = "failed" if str(action.get("status") or "") == "failed" else "completed"
            evidence = self._evidence_from_action(action)
            rows[source_key] = self._item(
                source_key=source_key,
                kind=str(task.get("kind") or outcome.get("kind") or "self_drive"),
                priority=int(task.get("priority") or 0),
                title=str(task.get("title") or "自走タスク"),
                reason=str(outcome.get("message") or task.get("reason") or ""),
                target=str(task.get("target") or "") or None,
                status=status,
                requires_human_approval=False,
                evidence_refs=evidence,
                updated_at=str(action.get("created_at") or now),
            )

        for task in drive.get("queue") or []:
            source_key = str(task.get("task_id") or "").strip()
            if not source_key:
                continue
            existing = rows.get(source_key)
            if existing is not None and existing.status in {"completed", "failed"}:
                continue
            rows[source_key] = self._item(
                source_key=source_key,
                kind=str(task.get("kind") or "self_drive"),
                priority=int(task.get("priority") or 0),
                title=str(task.get("title") or "自走タスク"),
                reason=str(task.get("reason") or ""),
                target=str(task.get("target") or "") or None,
                status="todo",
                requires_human_approval=bool(task.get("requires_human_approval")),
                evidence_refs=(),
                updated_at=now,
            )

        for mission in missions:
            if not (
                str(mission.get("status") or "") == "approval_required"
                or bool(mission.get("requires_approval"))
            ):
                continue
            mission_id = str(mission.get("mission_id") or "").strip()
            if not mission_id:
                continue
            source_key = "approval:" + mission_id
            rows[source_key] = self._item(
                source_key=source_key,
                kind="approval",
                priority=110,
                title="人の承認が必要",
                reason=str(mission.get("message") or "Build等の保護操作で承認待ちです。"),
                target=str(mission.get("project_slug") or "") or None,
                status="waiting_approval",
                requires_human_approval=True,
                evidence_refs=tuple(str(x) for x in mission.get("evidence_refs") or () if str(x).strip()),
                updated_at=str(mission.get("updated_at") or now),
            )

        ordered = sorted(
            rows.values(),
            key=lambda x: (
                self._status_order(x.status),
                -x.priority,
                x.title,
                x.backlog_id,
            ),
        )
        active = [x for x in ordered if x.status in {"todo", "waiting_approval"}]
        focus = active[:3]
        counts = {
            "todo": sum(1 for x in ordered if x.status == "todo"),
            "waiting_approval": sum(1 for x in ordered if x.status == "waiting_approval"),
            "completed": sum(1 for x in ordered if x.status == "completed"),
            "failed": sum(1 for x in ordered if x.status == "failed"),
        }
        snapshot = {
            "date": day,
            "generated_at": now,
            "self_drive_enabled": bool(drive.get("enabled")),
            "background_active": bool(drive.get("background_active")),
            "items": [x.to_dict() for x in ordered],
            "focus": [x.to_dict() for x in focus],
            "counts": counts,
            "safe_auto_count": counts["todo"],
            "approval_waiting": counts["waiting_approval"],
            "protected_execution_path": "SelfDriveEngine only",
            "rule": (
                "Backlog may prioritise and display safe work. Execution remains inside "
                "SelfDriveEngine; approval boundaries, production actions, main and Aivy "
                "source protections are unchanged."
            ),
        }
        with self._lock:
            self._write(snapshot)
        return snapshot

    def status(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self.refresh()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return self.refresh()
        if not isinstance(raw, dict) or str(raw.get("date") or "") != _local_day():
            return self.refresh()
        return raw

    def mark_refresh_after_action(self) -> dict[str, Any]:
        return self.refresh()

    @staticmethod
    def _status_order(status: str) -> int:
        return {
            "waiting_approval": 0,
            "todo": 1,
            "failed": 2,
            "completed": 3,
        }.get(status, 9)

    @staticmethod
    def _item(
        *,
        source_key: str,
        kind: str,
        priority: int,
        title: str,
        reason: str,
        target: str | None,
        status: str,
        requires_human_approval: bool,
        evidence_refs: tuple[str, ...],
        updated_at: str,
    ) -> BacklogItem:
        identity = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:20]
        return BacklogItem(
            backlog_id=identity,
            source_key=source_key,
            kind=kind[:80],
            priority=max(0, min(int(priority), 999)),
            title=title[:240],
            reason=reason[:1200],
            target=target[:240] if target else None,
            status=status,
            requires_human_approval=bool(requires_human_approval),
            evidence_refs=tuple(dict.fromkeys(evidence_refs))[:30],
            updated_at=updated_at,
        )

    @staticmethod
    def _evidence_from_action(action: dict[str, Any]) -> tuple[str, ...]:
        outcome = dict(action.get("outcome") or {})
        refs = [str(x) for x in outcome.get("evidence_refs") or () if str(x).strip()]
        if outcome.get("evidence_ref"):
            refs.append(str(outcome["evidence_ref"]))
        if outcome.get("run_id"):
            refs.append("run:" + str(outcome["run_id"]))
        return tuple(dict.fromkeys(refs))[:30]

    def _write(self, data: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
