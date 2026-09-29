from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Callable
import json
import time
import uuid

from .config import DATA_DIR


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


PROTECTED_ACTIONS = (
    "source_self_edit",
    "main_merge",
    "production_deploy",
    "external_publish",
    "billing",
    "secret_access",
    "production_database_write",
    "safety_policy_change",
    "permission_change",
    "approval_bypass",
)


@dataclass(frozen=True)
class SelfDriveTask:
    task_id: str
    kind: str
    priority: int
    title: str
    reason: str
    target: str | None
    safe_action: str
    requires_human_approval: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SelfDriveEngine:
    """Bounded autonomous scheduler for Aivy.

    A self-drive cycle chooses one useful safe task, executes it, records
    evidence, then stops. It never turns human approval into approval, never
    writes main, publishes externally, spends money, reads secrets, or edits
    Aivy source. Work that reaches a protected boundary remains waiting for a
    human decision.

    The engine is intentionally callback-driven so it can orchestrate existing
    reviewed Aivy capabilities instead of introducing a second execution path.
    """

    def __init__(
        self,
        *,
        list_projects: Callable[[], list[dict[str, Any]]],
        health_check: Callable[[str], dict[str, Any]],
        list_missions: Callable[[], list[dict[str, Any]]],
        safe_mission_cycle: Callable[[str], dict[str, Any]],
        growth_cycle: Callable[[], dict[str, Any]],
        practice_cycle: Callable[[], dict[str, Any]],
        settings_path: Path | None = None,
        history_path: Path | None = None,
    ):
        self.list_projects = list_projects
        self.health_check = health_check
        self.list_missions = list_missions
        self.safe_mission_cycle = safe_mission_cycle
        self.growth_cycle = growth_cycle
        self.practice_cycle = practice_cycle
        self.settings_path = settings_path or (DATA_DIR / "aivy_self_drive.json")
        self.history_path = history_path or (DATA_DIR / "aivy_self_drive_history.jsonl")
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self._cycle_lock = Lock()
        self._thread_lock = Lock()
        self._background_started = False

    def settings(self) -> dict[str, Any]:
        default = {
            "enabled": True,
            "interval_seconds": 600,
            "max_actions_per_cycle": 1,
            "project_health_cooldown_seconds": 21600,
            "mission_cooldown_seconds": 1800,
            "growth_cooldown_seconds": 1800,
            "practice_cooldown_seconds": 1800,
            "allow_source_self_edit": False,
            "allow_main_merge": False,
            "allow_production_deploy": False,
            "allow_external_publish": False,
            "allow_paid_actions": False,
            "allow_secret_access": False,
            "allow_production_database_write": False,
            "allow_safety_change": False,
            "allow_permission_change": False,
            "allow_approval_bypass": False,
        }
        if not self.settings_path.is_file():
            return default
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:
            return default
        if not isinstance(raw, dict):
            return default
        cfg = {**default, **raw}
        cfg["enabled"] = bool(cfg.get("enabled"))
        cfg["interval_seconds"] = max(300, min(int(cfg.get("interval_seconds") or 600), 86400))
        cfg["max_actions_per_cycle"] = 1
        for key in (
            "allow_source_self_edit",
            "allow_main_merge",
            "allow_production_deploy",
            "allow_external_publish",
            "allow_paid_actions",
            "allow_secret_access",
            "allow_production_database_write",
            "allow_safety_change",
            "allow_permission_change",
            "allow_approval_bypass",
        ):
            cfg[key] = False
        return cfg

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        cfg = self.settings()
        cfg["enabled"] = bool(enabled)
        cfg["updated_at"] = _now()
        self._write_json(self.settings_path, cfg)
        if enabled:
            self.start_background()
        return self.status()

    def start_background(self) -> bool:
        with self._thread_lock:
            if self._background_started:
                return False
            self._background_started = True
        Thread(
            target=self._background_loop,
            name="aivy-self-drive",
            daemon=True,
        ).start()
        return True

    def _background_loop(self) -> None:
        waiter = Event()
        while True:
            cfg = self.settings()
            waiter.wait(int(cfg["interval_seconds"]))
            if not self.settings().get("enabled"):
                continue
            try:
                self.run_cycle(trigger="background")
            except Exception:
                # Self-drive must never crash the host application.
                pass

    def status(self) -> dict[str, Any]:
        cfg = self.settings()
        history = self.recent(30)
        queue = self.plan()
        last = history[0] if history else None
        approvals = [
            row for row in self.list_missions()
            if str(row.get("status") or "") == "approval_required"
            or bool(row.get("requires_approval"))
        ]
        return {
            "enabled": bool(cfg["enabled"]),
            "background_active": self._background_started,
            "interval_seconds": int(cfg["interval_seconds"]),
            "max_actions_per_cycle": 1,
            "queue": [x.to_dict() for x in queue[:8]],
            "queue_count": len(queue),
            "approval_waiting": len(approvals),
            "last_action": last,
            "recent_actions": history[:10],
            "protected_actions": list(PROTECTED_ACTIONS),
            "source_self_edit_allowed": False,
            "main_merge_allowed": False,
            "production_deploy_allowed": False,
            "external_publish_allowed": False,
            "paid_actions_allowed": False,
            "secret_access_allowed": False,
            "production_database_write_allowed": False,
            "approval_bypass_allowed": False,
        }

    def plan(self) -> list[SelfDriveTask]:
        tasks: list[SelfDriveTask] = []
        recent = self.recent(200)
        cfg = self.settings()

        missions = self.list_missions()
        for mission in missions:
            status = str(mission.get("status") or "")
            mission_id = str(mission.get("mission_id") or "").strip()
            slug = str(mission.get("project_slug") or "").strip()
            if not mission_id or status in {"completed", "failed", "cancelled", "approval_required"}:
                continue
            if bool(mission.get("requires_approval")):
                continue
            if status == "running" and mission.get("build_job_id"):
                title = "進行中Missionの状態確認"
                priority = 100
                reason = "承認済みBuildの進行状態を安全に更新します。"
            elif status in {"queued", "paused"}:
                title = "Missionの安全な前処理"
                priority = 90
                reason = "Preflight・Sandbox・専門AI確認まで進め、Build承認地点で停止します。"
            else:
                continue
            key = f"mission:{mission_id}"
            if self._within_cooldown(
                recent,
                key,
                int(cfg["mission_cooldown_seconds"]),
            ):
                continue
            tasks.append(SelfDriveTask(
                task_id=key,
                kind="mission",
                priority=priority,
                title=title,
                reason=reason,
                target=slug or mission_id,
                safe_action=mission_id,
                requires_human_approval=False,
            ))

        projects = self.list_projects()
        for project in projects:
            slug = str(project.get("slug") or "").strip()
            if not slug:
                continue
            quality = str(project.get("quality") or "").upper()
            status = str(project.get("status") or "").lower()
            needs_check = quality != "PASS" or status in {
                "blocked", "issue", "attention_required", "draft", "needs_review"
            }
            if not needs_check:
                continue
            key = f"health:{slug}"
            if self._within_cooldown(
                recent,
                key,
                int(cfg["project_health_cooldown_seconds"]),
            ):
                continue
            tasks.append(SelfDriveTask(
                task_id=key,
                kind="project_health",
                priority=75,
                title="制作物の自動再点検",
                reason=f"quality={quality or 'unknown'} / status={status or 'unknown'} のため再検証します。",
                target=slug,
                safe_action=slug,
                requires_human_approval=False,
            ))

        if not self._within_cooldown(
            recent,
            "growth",
            int(cfg["growth_cooldown_seconds"]),
        ):
            tasks.append(SelfDriveTask(
                task_id="growth",
                kind="growth",
                priority=45,
                title="Verified経験の整理",
                reason="成功Evidenceを再利用Skillへ圧縮します。",
                target=None,
                safe_action="growth",
                requires_human_approval=False,
            ))

        if not self._within_cooldown(
            recent,
            "practice",
            int(cfg["practice_cooldown_seconds"]),
        ):
            tasks.append(SelfDriveTask(
                task_id="practice",
                kind="practice",
                priority=40,
                title="弱点の自主トレ",
                reason="Evidenceから最優先弱点を1件だけSynthetic Sandboxで練習します。",
                target=None,
                safe_action="practice",
                requires_human_approval=False,
            ))

        tasks.sort(key=lambda x: (-x.priority, x.kind, x.task_id))
        return tasks

    def run_cycle(self, *, trigger: str = "manual") -> dict[str, Any]:
        if not self._cycle_lock.acquire(blocking=False):
            return {
                "status": "busy",
                "trigger": trigger,
                "actions_executed": 0,
                "reason": "another self-drive cycle is already running",
            }
        try:
            cfg = self.settings()
            if not cfg.get("enabled"):
                result = {
                    "status": "disabled",
                    "trigger": trigger,
                    "actions_executed": 0,
                    "created_at": _now(),
                }
                self._append(result)
                return result

            queue = self.plan()
            if not queue:
                result = {
                    "status": "idle",
                    "trigger": trigger,
                    "actions_executed": 0,
                    "message": "No safe autonomous action is currently needed.",
                    "created_at": _now(),
                }
                self._append(result)
                return result

            task = queue[0]
            started = time.monotonic()
            outcome = self._execute(task)
            result = {
                "status": "completed",
                "trigger": trigger,
                "actions_executed": 1,
                "task": task.to_dict(),
                "outcome": outcome,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "created_at": _now(),
                "protected_actions_unchanged": True,
                "approval_bypassed": False,
                "source_code_mutated": False,
                "main_merged": False,
                "external_published": False,
                "paid_action": False,
            }
            self._append(result)
            return result
        finally:
            self._cycle_lock.release()

    def _execute(self, task: SelfDriveTask) -> dict[str, Any]:
        if task.kind == "mission":
            row = self.safe_mission_cycle(task.safe_action)
            return {
                "kind": "mission",
                "mission_id": task.safe_action,
                "status": row.get("status"),
                "phase": row.get("phase"),
                "requires_approval": bool(row.get("requires_approval")),
                "message": row.get("message"),
                "evidence_refs": list(row.get("evidence_refs") or ()),
            }
        if task.kind == "project_health":
            row = self.health_check(task.safe_action)
            return {
                "kind": "project_health",
                "project_slug": task.safe_action,
                "status": row.get("status"),
                "tests_passed": bool(row.get("tests_passed")),
                "design_passed": bool(row.get("design_passed")),
                "security_passed": bool(row.get("security_passed")),
                "run_id": row.get("run_id"),
            }
        if task.kind == "growth":
            row = self.growth_cycle()
            return {
                "kind": "growth",
                "status": row.get("status"),
                "skills_added": int(row.get("skills_added") or 0),
                "skills_updated": int(row.get("skills_updated") or 0),
                "total_skills": int(row.get("total_skills") or 0),
            }
        if task.kind == "practice":
            row = self.practice_cycle()
            promotion = dict(row.get("promotion") or {})
            return {
                "kind": "practice",
                "status": row.get("status"),
                "promoted": bool(promotion.get("promoted")),
                "evidence_ref": row.get("evidence_ref"),
            }
        raise ValueError(f"unsupported self-drive task: {task.kind}")

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.history_path.is_file():
            return []
        try:
            lines = self.history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        rows: list[dict[str, Any]] = []
        for line in lines[-max(1, min(int(limit), 500)):]:
            try:
                raw = json.loads(line)
                if isinstance(raw, dict):
                    rows.append(raw)
            except Exception:
                continue
        return list(reversed(rows))

    @staticmethod
    def _within_cooldown(
        recent: list[dict[str, Any]],
        task_id: str,
        cooldown_seconds: int,
    ) -> bool:
        now = datetime.now(timezone.utc)
        for row in recent:
            task = row.get("task") or {}
            if str(task.get("task_id") or "") != task_id:
                continue
            raw_at = str(row.get("created_at") or "")
            if not raw_at:
                continue
            try:
                at = datetime.fromisoformat(raw_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            return (now - at).total_seconds() < max(0, int(cooldown_seconds))
        return False

    def _append(self, row: dict[str, Any]) -> None:
        payload = dict(row)
        payload.setdefault("event_id", uuid.uuid4().hex)
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
