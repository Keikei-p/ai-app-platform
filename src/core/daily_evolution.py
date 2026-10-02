from __future__ import annotations

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


def _local_day() -> str:
    return datetime.now().astimezone().date().isoformat()


PROTECTED_SCOPE = (
    "aivy_source",
    "main_branch",
    "secrets",
    "billing",
    "external_publish",
    "production_database",
    "safety",
    "security_policy",
    "permissions",
    "approval",
)


class DailyEvolutionEngine:
    """Run one bounded, evidence-backed Aivy evolution cycle per local day.

    A cycle compacts verified learning into reusable Skills, runs at most one
    synthetic self-practice task, refreshes the daily backlog, and writes a
    persistent report. It never edits Aivy source, main, production systems,
    secrets, billing, permissions, safety policy or approval state.

    If Aivy was offline when the date changed, the first startup/check on the
    next day catches up automatically. No fixed wall-clock time is required.
    """

    def __init__(
        self,
        *,
        growth_cycle: Callable[[], dict[str, Any]],
        growth_status: Callable[[], dict[str, Any]],
        practice_cycle: Callable[[], dict[str, Any]],
        practice_status: Callable[[], dict[str, Any]],
        backlog_refresh: Callable[[], dict[str, Any]],
        settings_path: Path | None = None,
        history_path: Path | None = None,
    ):
        self.growth_cycle = growth_cycle
        self.growth_status = growth_status
        self.practice_cycle = practice_cycle
        self.practice_status = practice_status
        self.backlog_refresh = backlog_refresh
        self.settings_path = settings_path or (DATA_DIR / "aivy_daily_evolution.json")
        self.history_path = history_path or (DATA_DIR / "aivy_daily_evolution_history.jsonl")
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self._cycle_lock = Lock()
        self._thread_lock = Lock()
        self._background_started = False

    def settings(self) -> dict[str, Any]:
        default = {
            "enabled": True,
            "check_interval_seconds": 1800,
            "max_practice_tasks_per_day": 1,
            "allow_source_self_edit": False,
            "allow_main_merge": False,
            "allow_external_publish": False,
            "allow_paid_actions": False,
            "allow_secret_access": False,
            "allow_production_database_write": False,
            "allow_safety_change": False,
            "allow_permission_change": False,
            "allow_approval_bypass": False,
        }
        raw = self._read_settings_raw()
        cfg = {**default, **raw}
        cfg["enabled"] = bool(cfg.get("enabled"))
        cfg["check_interval_seconds"] = max(
            900,
            min(int(cfg.get("check_interval_seconds") or 1800), 21600),
        )
        cfg["max_practice_tasks_per_day"] = 1
        for key in (
            "allow_source_self_edit",
            "allow_main_merge",
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
        raw = self._read_settings_raw()
        raw.update(self.settings())
        raw["enabled"] = bool(enabled)
        raw["updated_at"] = _now()
        self._write_json(self.settings_path, raw)
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
            name="aivy-daily-evolution",
            daemon=True,
        ).start()
        return True

    def _background_loop(self) -> None:
        waiter = Event()
        while True:
            try:
                self.run_if_due(trigger="background")
            except Exception:
                # Daily evolution must never crash the host application.
                pass
            interval = int(self.settings()["check_interval_seconds"])
            waiter.wait(interval)

    def status(self) -> dict[str, Any]:
        cfg = self.settings()
        raw = self._read_settings_raw()
        today = _local_day()
        last_completed_day = str(raw.get("last_completed_day") or "")
        growth = self.growth_status()
        practice = self.practice_status()
        return {
            "enabled": bool(cfg["enabled"]),
            "background_active": self._background_started,
            "today": today,
            "due_today": bool(cfg["enabled"] and last_completed_day != today),
            "last_completed_day": last_completed_day or None,
            "last_run_at": raw.get("last_run_at"),
            "last_result": raw.get("last_result"),
            "check_interval_seconds": int(cfg["check_interval_seconds"]),
            "max_practice_tasks_per_day": 1,
            "skills": int(growth.get("skills") or 0),
            "verified_examples": int(growth.get("verified_examples") or 0),
            "weaknesses": len(practice.get("weaknesses") or []),
            "practice_queue": len(practice.get("practice_queue") or []),
            "protected_scope": list(PROTECTED_SCOPE),
            "source_self_edit_allowed": False,
            "main_merge_allowed": False,
            "external_publish_allowed": False,
            "paid_actions_allowed": False,
            "secret_access_allowed": False,
            "production_database_write_allowed": False,
            "approval_bypass_allowed": False,
        }

    def run_if_due(
        self,
        *,
        trigger: str = "manual",
        force: bool = False,
    ) -> dict[str, Any]:
        if not self._cycle_lock.acquire(blocking=False):
            return {
                "status": "busy",
                "trigger": trigger,
                "ran": False,
                "reason": "another daily evolution cycle is already running",
            }
        try:
            cfg = self.settings()
            today = _local_day()
            raw = self._read_settings_raw()

            if not cfg["enabled"] and not force:
                return self._record({
                    "status": "disabled",
                    "trigger": trigger,
                    "ran": False,
                    "day": today,
                    "created_at": _now(),
                })

            if not force and str(raw.get("last_completed_day") or "") == today:
                return {
                    "status": "already_completed_today",
                    "trigger": trigger,
                    "ran": False,
                    "day": today,
                    "last_run_at": raw.get("last_run_at"),
                    "last_result": raw.get("last_result"),
                }

            before_growth = self.growth_status()
            before_practice = self.practice_status()
            started = time.monotonic()

            growth_result: dict[str, Any]
            practice_result: dict[str, Any]
            backlog_result: dict[str, Any]
            errors: list[dict[str, str]] = []

            try:
                growth_result = self.growth_cycle()
            except Exception as exc:
                growth_result = {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:1000],
                }
                errors.append({
                    "stage": "growth",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:1000],
                })

            try:
                practice_result = self.practice_cycle()
            except Exception as exc:
                practice_result = {
                    "status": "failed",
                    "promotion": {"promoted": False},
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:1000],
                }
                errors.append({
                    "stage": "practice",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:1000],
                })

            try:
                backlog_result = self.backlog_refresh()
            except Exception as exc:
                backlog_result = {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:1000],
                }
                errors.append({
                    "stage": "backlog",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:1000],
                })

            after_growth = self.growth_status()
            after_practice = self.practice_status()
            promotion = dict(practice_result.get("promotion") or {})
            result = {
                "status": "completed" if not errors else "partial",
                "trigger": trigger,
                "ran": True,
                "day": today,
                "created_at": _now(),
                "duration_ms": int((time.monotonic() - started) * 1000),
                "growth": growth_result,
                "practice": practice_result,
                "backlog": {
                    "date": backlog_result.get("date"),
                    "counts": backlog_result.get("counts"),
                    "focus": backlog_result.get("focus"),
                },
                "evolution_delta": {
                    "skills_before": int(before_growth.get("skills") or 0),
                    "skills_after": int(after_growth.get("skills") or 0),
                    "skills_added_today": max(
                        0,
                        int(after_growth.get("skills") or 0)
                        - int(before_growth.get("skills") or 0),
                    ),
                    "weaknesses_before": len(before_practice.get("weaknesses") or []),
                    "weaknesses_after": len(after_practice.get("weaknesses") or []),
                    "practice_promoted": bool(promotion.get("promoted")),
                },
                "errors": errors,
                "protected_scope_unchanged": True,
                "source_code_mutated": False,
                "main_merged": False,
                "external_published": False,
                "paid_action": False,
                "production_data_written": False,
                "approval_bypassed": False,
            }

            # Only a fully completed cycle satisfies today's automatic evolution.
            # Partial failures remain due and are retried at the next background check.
            if not errors:
                result["completed_day"] = today
            return self._record(result)
        finally:
            self._cycle_lock.release()

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

    def _record(self, result: dict[str, Any]) -> dict[str, Any]:
        raw = self._read_settings_raw()
        raw.update(self.settings())
        raw["last_run_at"] = result.get("created_at") or _now()
        raw["last_result"] = result
        if result.get("status") == "completed" and result.get("completed_day"):
            raw["last_completed_day"] = str(result["completed_day"])
        self._write_json(self.settings_path, raw)

        payload = dict(result)
        payload.setdefault("event_id", uuid.uuid4().hex)
        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return result

    def _read_settings_raw(self) -> dict[str, Any]:
        if not self.settings_path.is_file():
            return {}
        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
