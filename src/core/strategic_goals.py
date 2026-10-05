from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable
import hashlib
import json
import uuid

from .config import DATA_DIR
from .redaction import redact_sensitive


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StrategicGoal:
    goal_id: str
    project_slug: str
    objective: str
    status: str
    created_at: str
    updated_at: str
    max_auto_missions: int = 12
    missions_created: int = 0
    current_mission_id: str | None = None
    completed_mission_ids: list[str] = field(default_factory=list)
    last_decision: str = ""
    last_evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StrategicGoalStore:
    """Persistent long-term goals for Aivy's safe autonomous mission planning."""

    TERMINAL = {"completed", "cancelled"}

    def __init__(self, path: Path | None = None):
        self.path = path or (DATA_DIR / "aivy_strategic_goals.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def create(
        self,
        *,
        project_slug: str,
        objective: str,
        max_auto_missions: int = 12,
    ) -> StrategicGoal:
        slug = redact_sensitive(str(project_slug or "").strip())[:180]
        goal = redact_sensitive(str(objective or "").strip())[:6000]
        if not slug or not goal:
            raise ValueError("project_slug and objective are required")
        now = _now()
        item = StrategicGoal(
            goal_id=uuid.uuid4().hex,
            project_slug=slug,
            objective=goal,
            status="active",
            created_at=now,
            updated_at=now,
            max_auto_missions=max(1, min(int(max_auto_missions), 32)),
            last_decision="Long-term goal created. Aivy may generate safe Missions toward it.",
        )
        with self._lock:
            rows = self._read()
            rows[item.goal_id] = item
            self._write(rows)
        return item

    def list(self, limit: int = 100) -> list[StrategicGoal]:
        rows = list(self._read().values())
        rows.sort(key=lambda x: (x.status != "active", x.updated_at), reverse=False)
        return rows[: max(1, min(int(limit), 500))]

    def get(self, goal_id: str) -> StrategicGoal:
        item = self._read().get(str(goal_id).strip())
        if item is None:
            raise KeyError(goal_id)
        return item

    def update(self, goal_id: str, **changes: Any) -> StrategicGoal:
        with self._lock:
            rows = self._read()
            item = rows.get(str(goal_id).strip())
            if item is None:
                raise KeyError(goal_id)
            if item.status in self.TERMINAL and changes.get("status") not in {None, item.status}:
                raise ValueError("terminal strategic goal cannot transition")
            for key, value in changes.items():
                if key == "status" and value is not None:
                    item.status = str(value)[:80]
                elif key == "missions_created" and value is not None:
                    item.missions_created = max(0, int(value))
                elif key == "current_mission_id":
                    item.current_mission_id = str(value).strip()[:180] if value else None
                elif key == "completed_mission_ids" and value is not None:
                    item.completed_mission_ids = list(dict.fromkeys(
                        str(x).strip()[:180] for x in value if str(x).strip()
                    ))[-100:]
                elif key == "last_decision" and value is not None:
                    item.last_decision = redact_sensitive(str(value))[:2000]
                elif key == "last_evidence" and value is not None:
                    item.last_evidence = list(dict.fromkeys(
                        redact_sensitive(str(x).strip())[:500]
                        for x in value if str(x).strip()
                    ))[-100:]
            item.updated_at = _now()
            rows[item.goal_id] = item
            self._write(rows)
            return item

    def pause(self, goal_id: str) -> StrategicGoal:
        return self.update(
            goal_id,
            status="paused",
            last_decision="Long-term goal paused. Existing Mission state is preserved.",
        )

    def resume(self, goal_id: str) -> StrategicGoal:
        item = self.get(goal_id)
        if item.status in self.TERMINAL:
            return item
        return self.update(
            goal_id,
            status="active",
            last_decision="Long-term goal resumed.",
        )

    def cancel(self, goal_id: str) -> StrategicGoal:
        return self.update(
            goal_id,
            status="cancelled",
            last_decision="Long-term goal cancelled without deleting project or Mission data.",
        )

    def _read(self) -> dict[str, StrategicGoal]:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        rows: dict[str, StrategicGoal] = {}
        for row in raw if isinstance(raw, list) else []:
            try:
                item = StrategicGoal(
                    goal_id=str(row["goal_id"]),
                    project_slug=str(row["project_slug"]),
                    objective=str(row["objective"]),
                    status=str(row.get("status") or "active"),
                    created_at=str(row.get("created_at") or _now()),
                    updated_at=str(row.get("updated_at") or _now()),
                    max_auto_missions=max(1, min(int(row.get("max_auto_missions") or 12), 32)),
                    missions_created=max(0, int(row.get("missions_created") or 0)),
                    current_mission_id=str(row.get("current_mission_id") or "") or None,
                    completed_mission_ids=[str(x) for x in row.get("completed_mission_ids") or ()],
                    last_decision=str(row.get("last_decision") or ""),
                    last_evidence=[str(x) for x in row.get("last_evidence") or ()],
                )
                rows[item.goal_id] = item
            except Exception:
                continue
        return rows

    def _write(self, rows: dict[str, StrategicGoal]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps([x.to_dict() for x in rows.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)


class StrategicAutonomyEngine:
    """Generate at most one safe Mission at a time from persistent long-term goals.

    This engine may create Mission *plans*. It never approves builds, deploys,
    spends money, edits main, accesses secrets or changes safety/permissions.
    SelfDrive/MissionControl remain the only reviewed execution path.
    """

    OPEN_MISSION_STATUSES = {
        "queued", "running", "paused", "approval_required",
    }

    def __init__(
        self,
        *,
        store: StrategicGoalStore,
        list_projects: Callable[[], list[dict[str, Any]]],
        project_detail: Callable[[str], dict[str, Any]],
        list_missions: Callable[[], list[dict[str, Any]]],
        create_mission: Callable[..., dict[str, Any]],
        history_path: Path | None = None,
    ):
        self.store = store
        self.list_projects = list_projects
        self.project_detail = project_detail
        self.list_missions = list_missions
        self.create_mission = create_mission
        self.history_path = history_path or (DATA_DIR / "aivy_strategic_history.jsonl")
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def status(self) -> dict[str, Any]:
        goals = self.store.list(200)
        active = [x for x in goals if x.status == "active"]
        waiting = [x for x in active if x.current_mission_id]
        return {
            "goals": [x.to_dict() for x in goals],
            "active_goals": len(active),
            "waiting_on_mission": len(waiting),
            "last_result": self.recent(1)[0] if self.recent(1) else None,
            "max_missions_created_per_cycle": 1,
            "build_auto_approval": False,
            "production_deploy_allowed": False,
            "source_self_edit_allowed": False,
            "main_merge_allowed": False,
            "paid_actions_allowed": False,
            "secret_access_allowed": False,
            "approval_bypass_allowed": False,
        }

    def create_goal(
        self,
        *,
        project_slug: str,
        objective: str,
        max_auto_missions: int = 12,
    ) -> dict[str, Any]:
        projects = {str(x.get("slug") or "") for x in self.list_projects()}
        if project_slug not in projects:
            raise FileNotFoundError(project_slug)
        return self.store.create(
            project_slug=project_slug,
            objective=objective,
            max_auto_missions=max_auto_missions,
        ).to_dict()

    def run_cycle(self, *, trigger: str = "daily") -> dict[str, Any]:
        with self._lock:
            missions = self.list_missions()
            mission_by_id = {
                str(x.get("mission_id") or ""): x
                for x in missions
                if str(x.get("mission_id") or "")
            }
            projects = {
                str(x.get("slug") or ""): x
                for x in self.list_projects()
                if str(x.get("slug") or "")
            }

            for goal in self.store.list(200):
                if goal.status != "active":
                    continue
                if goal.project_slug not in projects:
                    row = self.store.update(
                        goal.goal_id,
                        status="paused",
                        last_decision="Project is missing. Strategic goal paused safely.",
                    )
                    return self._record({
                        "status": "paused",
                        "trigger": trigger,
                        "goal": row.to_dict(),
                        "mission_created": False,
                        "reason": "project_missing",
                        "created_at": _now(),
                    })

                if goal.current_mission_id:
                    current = mission_by_id.get(goal.current_mission_id)
                    if current is None:
                        self.store.update(
                            goal.goal_id,
                            current_mission_id=None,
                            last_decision="Previous Mission record was unavailable; goal will re-plan safely.",
                        )
                        continue
                    status = str(current.get("status") or "")
                    if status in self.OPEN_MISSION_STATUSES:
                        return self._record({
                            "status": "waiting_on_mission",
                            "trigger": trigger,
                            "goal_id": goal.goal_id,
                            "mission_id": goal.current_mission_id,
                            "mission_status": status,
                            "mission_created": False,
                            "requires_approval": bool(current.get("requires_approval")),
                            "created_at": _now(),
                        })
                    completed_ids = list(goal.completed_mission_ids)
                    if status == "completed" and goal.current_mission_id not in completed_ids:
                        completed_ids.append(goal.current_mission_id)
                    decision = (
                        f"Previous Mission ended with status={status}. "
                        "Aivy may create the next bounded milestone."
                    )
                    goal = self.store.update(
                        goal.goal_id,
                        current_mission_id=None,
                        completed_mission_ids=completed_ids,
                        last_decision=decision,
                        last_evidence=[str(x) for x in current.get("evidence_refs") or ()],
                    )

                if goal.missions_created >= goal.max_auto_missions:
                    row = self.store.update(
                        goal.goal_id,
                        status="paused",
                        last_decision="Auto-Mission budget reached. Human review is required before more Missions.",
                    )
                    return self._record({
                        "status": "mission_budget_reached",
                        "trigger": trigger,
                        "goal": row.to_dict(),
                        "mission_created": False,
                        "created_at": _now(),
                    })

                project = projects[goal.project_slug]
                detail = self.project_detail(goal.project_slug)
                mission_goal = self._next_mission_goal(goal, project, detail)
                mission = self.create_mission(
                    goal=mission_goal,
                    project_slug=goal.project_slug,
                    max_cycles=8,
                )
                mission_id = str(mission.get("mission_id") or "").strip()
                if not mission_id:
                    raise RuntimeError("Mission creation did not return mission_id")

                row = self.store.update(
                    goal.goal_id,
                    missions_created=goal.missions_created + 1,
                    current_mission_id=mission_id,
                    last_decision=(
                        "Created one bounded Mission from the long-term goal. "
                        "SelfDrive may preflight it, but Build requires human approval."
                    ),
                    last_evidence=[f"mission:{mission_id}"],
                )
                return self._record({
                    "status": "mission_created",
                    "trigger": trigger,
                    "goal": row.to_dict(),
                    "mission": mission,
                    "mission_created": True,
                    "build_auto_approved": False,
                    "created_at": _now(),
                })

            return self._record({
                "status": "no_active_goal",
                "trigger": trigger,
                "mission_created": False,
                "created_at": _now(),
            })

    def _next_mission_goal(
        self,
        goal: StrategicGoal,
        project: dict[str, Any],
        detail: dict[str, Any],
    ) -> str:
        quality = str(project.get("quality") or "").upper()
        status = str(project.get("status") or "").lower()
        readiness = dict(detail.get("readiness") or {})
        gaps_raw = detail.get("gaps") or {}
        gaps = list(gaps_raw.get("items") or []) if isinstance(gaps_raw, dict) else []
        blockers = [
            str(x.get("reason") or x.get("title") or "").strip()
            for x in gaps[:6]
            if isinstance(x, dict)
            and str(x.get("reason") or x.get("title") or "").strip()
        ]

        step = goal.missions_created + 1
        prefix = (
            f"長期目標「{goal.objective}」へ近づける第{step}Mission。"
            "既存機能を壊さず、Evidence付きで改善する。"
        )
        if quality != "PASS":
            return (
                prefix
                + f" 現在quality={quality or 'UNKNOWN'}。"
                + " Tests / Design / Security / Regressionの失敗原因を特定し、"
                + "Release Gateを通せる状態へ改善する。"
                + (f" 既知の未完了: {' / '.join(blockers)}" if blockers else "")
            )
        if not bool(readiness.get("preview_ready")):
            return (
                prefix
                + " Previewが未準備。主要ユーザーフローを実行可能にし、"
                "レスポンシブ表示・エラー状態・主要操作を検証する。"
            )
        if not bool(readiness.get("release_ready")):
            return (
                prefix
                + " Release Readyではない。未完了EvidenceとGuardian結果を確認し、"
                "公開前品質まで改善する。ただし外部公開自体は行わない。"
                + (f" 既知の未完了: {' / '.join(blockers)}" if blockers else "")
            )
        return (
            prefix
            + f" 現在status={status or 'unknown'} / quality={quality or 'unknown'}。"
            " 次の価値ある改善を1つに絞り、利用者体験・信頼性・保守性のいずれかを"
            " measurableに改善し、回帰テストとEvidenceを残す。"
        )

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        if not self.history_path.is_file():
            return []
        try:
            lines = self.history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        rows: list[dict[str, Any]] = []
        for line in lines[-max(1, min(int(limit), 365)):]:
            try:
                raw = json.loads(line)
                if isinstance(raw, dict):
                    rows.append(raw)
            except Exception:
                continue
        return list(reversed(rows))

    def _record(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = dict(row)
        payload.setdefault("event_id", uuid.uuid4().hex)
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return row
