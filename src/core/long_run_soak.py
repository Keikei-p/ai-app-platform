from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Callable
import json

from .config import DATA_DIR, ROOT_DIR


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class LongRunSoakMonitor:
    """Persist real wall-clock Aivy stability evidence.

    Unit tests may use a fake clock to verify arithmetic, but Completion Readiness
    only reads this monitor's real runtime state. A soak becomes verified only
    after the persisted session has actually covered the target duration with
    enough healthy samples and no oversized monitoring gap.
    """

    TARGET_SECONDS = 24 * 60 * 60
    HEARTBEAT_SECONDS = 15 * 60
    MAX_GAP_SECONDS = 45 * 60
    MIN_SAMPLES = 80

    SOURCE_PATHS = (
        "src/core/self_drive.py",
        "src/core/daily_evolution.py",
        "src/core/strategic_goals.py",
        "src/core/platform_service.py",
        "src/core/long_run_soak.py",
    )

    def __init__(
        self,
        *,
        self_drive_status: Callable[[], dict[str, Any]],
        daily_evolution_status: Callable[[], dict[str, Any]],
        strategic_status: Callable[[], dict[str, Any]],
        health_status: Callable[[], dict[str, Any]],
        root_dir: Path | None = None,
        state_path: Path | None = None,
        now_fn: Callable[[], datetime] | None = None,
        target_seconds: int | None = None,
        heartbeat_seconds: int | None = None,
        max_gap_seconds: int | None = None,
        min_samples: int | None = None,
    ):
        self.self_drive_status = self_drive_status
        self.daily_evolution_status = daily_evolution_status
        self.strategic_status = strategic_status
        self.health_status = health_status
        self.root_dir = Path(root_dir or ROOT_DIR)
        self.state_path = Path(
            state_path or (DATA_DIR / "completion_evidence" / "long_run_soak.json")
        )
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_path = self.state_path.with_suffix(self.state_path.suffix + ".bak")
        self.now_fn = now_fn or _utc_now
        self.target_seconds = max(60, int(target_seconds or self.TARGET_SECONDS))
        self.heartbeat_seconds = max(30, int(heartbeat_seconds or self.HEARTBEAT_SECONDS))
        self.max_gap_seconds = max(
            self.heartbeat_seconds,
            int(max_gap_seconds or self.MAX_GAP_SECONDS),
        )
        self.min_samples = max(2, int(min_samples or self.MIN_SAMPLES))
        self._state_lock = Lock()
        self._thread_lock = Lock()
        self._background_started = False

    def start_background(self) -> bool:
        with self._thread_lock:
            if self._background_started:
                return False
            self._background_started = True
        self.ensure_active()
        Thread(
            target=self._background_loop,
            name="aivy-long-run-soak",
            daemon=True,
        ).start()
        return True

    def _background_loop(self) -> None:
        waiter = Event()
        while True:
            try:
                self.checkpoint(trigger="background")
            except Exception:
                # Monitoring must never crash Aivy.
                pass
            waiter.wait(self.heartbeat_seconds)

    def ensure_active(self) -> dict[str, Any]:
        with self._state_lock:
            raw = self._read()
            now = self._now()
            if not raw or str(raw.get("status") or "") in {
                "failed",
                "invalidated",
                "stopped",
            }:
                raw = self._new_session(now)
                self._write(raw)
                return raw

            if raw.get("verified") is True:
                return raw

            expected = raw.get("source_blobs")
            current = self.source_blobs()
            if not isinstance(expected, dict) or expected != current:
                raw = self._new_session(now)
                raw["restart_reason"] = "covered source changed; new soak window started"
                self._write(raw)
            return raw

    def start(self, *, reset: bool = False) -> dict[str, Any]:
        with self._state_lock:
            raw = self._read()
            if raw and not reset and str(raw.get("status") or "") == "running":
                return self._status_from(raw, self._now())
            raw = self._new_session(self._now())
            raw["restart_reason"] = "manual reset" if reset else "manual start"
            self._write(raw)
            return self._status_from(raw, self._now())

    def stop(self) -> dict[str, Any]:
        with self._state_lock:
            raw = self._read()
            if not raw:
                raw = self._new_session(self._now())
            raw["status"] = "stopped"
            raw["verified"] = False
            raw["stopped_at"] = _iso(self._now())
            self._write(raw)
            return self._status_from(raw, self._now())

    def checkpoint(self, *, trigger: str = "manual") -> dict[str, Any]:
        with self._state_lock:
            raw = self._read()
            now = self._now()
            if not raw or str(raw.get("status") or "") in {
                "failed",
                "invalidated",
                "stopped",
            }:
                raw = self._new_session(now)

            # Wall-clock regressions invalidate continuous-duration evidence.
            # Do this before returning an already verified session.
            started_at = _parse(raw.get("started_at"))
            last_sample_at = _parse(raw.get("last_sample_at"))
            if (
                (started_at is not None and now < started_at)
                or (last_sample_at is not None and now < last_sample_at)
            ):
                raw = self._new_session(now)
                raw["restart_reason"] = "system clock moved backwards; new soak window started"

            if raw.get("verified") is True:
                return self._status_from(raw, now)

            current_blobs = self.source_blobs()
            if raw.get("source_blobs") != current_blobs:
                raw = self._new_session(now)
                raw["restart_reason"] = "covered source changed; new soak window started"

            samples = list(raw.get("samples") or [])
            previous = _parse(str((samples[-1] if samples else {}).get("at") or ""))
            gap_seconds = (
                max(0.0, (now - previous).total_seconds())
                if previous is not None
                else 0.0
            )
            if previous is not None and gap_seconds > self.max_gap_seconds:
                raw = self._new_session(now)
                raw["restart_reason"] = (
                    f"monitoring gap {int(gap_seconds)}s exceeded "
                    f"{self.max_gap_seconds}s; new soak window started"
                )
                samples = []

            sample = self._sample(now, trigger)
            samples = list(raw.get("samples") or [])
            samples.append(sample)
            # 24h at 15-minute cadence is ~97 rows. Keep a bounded audit window.
            raw["samples"] = samples[-max(200, self.min_samples * 2):]
            raw["last_sample_at"] = sample["at"]
            raw["sample_count"] = len(raw["samples"])
            raw["failure_count"] = sum(
                1 for row in raw["samples"] if row.get("ok") is not True
            )
            if sample["ok"] is not True:
                raw["last_failure"] = {
                    "at": sample["at"],
                    "reasons": list(sample.get("reasons") or []),
                }

            started = _parse(raw.get("started_at")) or now
            elapsed = max(0.0, (now - started).total_seconds())
            raw["elapsed_seconds"] = int(elapsed)
            raw["progress_percent"] = round(
                min(100.0, elapsed / self.target_seconds * 100),
                2,
            )

            enough_time = elapsed >= self.target_seconds
            enough_samples = int(raw.get("sample_count") or 0) >= self.min_samples
            no_failures = int(raw.get("failure_count") or 0) == 0
            source_unchanged = raw.get("source_blobs") == self.source_blobs()
            sources_present = not self._missing_source_paths()
            verified = bool(
                enough_time
                and enough_samples
                and no_failures
                and source_unchanged
                and sources_present
            )
            raw["verified"] = verified
            raw["status"] = "verified" if verified else "running"
            if verified:
                raw["verified_at"] = _iso(now)

            self._write(raw)
            return self._status_from(raw, now)

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            raw = self._read()
            now = self._now()
            if not raw:
                return {
                    **self._new_session(now),
                    "status": "not_started",
                    "verified": False,
                    "background_active": self._background_started,
                }

            started_at = _parse(raw.get("started_at"))
            last_sample_at = _parse(raw.get("last_sample_at"))
            if (
                (started_at is not None and now < started_at)
                or (last_sample_at is not None and now < last_sample_at)
            ):
                return {
                    **self._status_from(raw, now),
                    "status": "stale",
                    "verified": False,
                    "stale": True,
                    "reason": "system clock moved backwards since soak evidence",
                }
            if self._missing_source_paths():
                return {
                    **self._status_from(raw, now),
                    "status": "stale",
                    "verified": False,
                    "stale": True,
                    "reason": "covered source file missing",
                }
            if raw.get("source_blobs") != self.source_blobs():
                return {
                    **self._status_from(raw, now),
                    "status": "stale",
                    "verified": False,
                    "stale": True,
                    "reason": "covered source changed since soak started",
                }
            return self._status_from(raw, now)

    def _sample(self, now: datetime, trigger: str) -> dict[str, Any]:
        reasons: list[str] = []
        snapshots: dict[str, Any] = {}

        try:
            drive = dict(self.self_drive_status() or {})
            snapshots["self_drive"] = {
                "enabled": bool(drive.get("enabled")),
                "background_active": bool(drive.get("background_active")),
                "approval_bypass_allowed": drive.get("approval_bypass_allowed"),
            }
            if drive.get("enabled") is not True:
                reasons.append("self_drive_disabled")
            if drive.get("background_active") is not True:
                reasons.append("self_drive_background_inactive")
            if drive.get("approval_bypass_allowed") is not False:
                reasons.append("self_drive_approval_boundary_invalid")
        except Exception as exc:
            reasons.append("self_drive_status_error:" + type(exc).__name__)

        try:
            daily = dict(self.daily_evolution_status() or {})
            snapshots["daily_evolution"] = {
                "enabled": bool(daily.get("enabled")),
                "background_active": bool(daily.get("background_active")),
                "source_self_edit_allowed": daily.get("source_self_edit_allowed"),
            }
            if daily.get("enabled") is not True:
                reasons.append("daily_evolution_disabled")
            if daily.get("background_active") is not True:
                reasons.append("daily_evolution_background_inactive")
            if daily.get("source_self_edit_allowed") is not False:
                reasons.append("daily_evolution_source_protection_invalid")
        except Exception as exc:
            reasons.append("daily_evolution_status_error:" + type(exc).__name__)

        try:
            strategy = dict(self.strategic_status() or {})
            snapshots["strategy"] = {
                "active_goals": int(strategy.get("active_goals") or 0),
                "waiting_on_mission": int(strategy.get("waiting_on_mission") or 0),
                "build_auto_approval": strategy.get("build_auto_approval"),
            }
            if strategy.get("build_auto_approval") is not False:
                reasons.append("strategy_auto_approval_boundary_invalid")
        except Exception as exc:
            reasons.append("strategy_status_error:" + type(exc).__name__)

        try:
            health = dict(self.health_status() or {})
            health_state = str(health.get("status") or "unknown").lower()
            snapshots["health"] = {"status": health_state}
            if health_state in {"failed", "critical"}:
                reasons.append("health_" + health_state)
        except Exception as exc:
            reasons.append("health_status_error:" + type(exc).__name__)

        if self._missing_source_paths():
            reasons.append("covered_source_missing")

        return {
            "at": _iso(now),
            "trigger": str(trigger)[:80],
            "ok": not reasons,
            "reasons": reasons,
            "snapshots": snapshots,
        }

    def _new_session(self, now: datetime) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": "long_run_soak",
            "session_id": _iso(now),
            "status": "running",
            "verified": False,
            "started_at": _iso(now),
            "last_sample_at": None,
            "verified_at": None,
            "target_seconds": self.target_seconds,
            "heartbeat_seconds": self.heartbeat_seconds,
            "max_gap_seconds": self.max_gap_seconds,
            "min_samples": self.min_samples,
            "sample_count": 0,
            "failure_count": 0,
            "elapsed_seconds": 0,
            "progress_percent": 0.0,
            "samples": [],
            "source_blobs": self.source_blobs(),
            "external_actions": False,
            "credentials_used": False,
            "paid_actions": False,
            "production_data_written": False,
            "created_at": _iso(now),
        }

    def _status_from(self, raw: dict[str, Any], now: datetime) -> dict[str, Any]:
        started = _parse(raw.get("started_at"))
        elapsed = (
            max(0.0, (now - started).total_seconds())
            if started is not None
            else 0.0
        )
        target = max(1, int(raw.get("target_seconds") or self.target_seconds))
        result = dict(raw)
        result["elapsed_seconds"] = int(elapsed)
        result["progress_percent"] = round(min(100.0, elapsed / target * 100), 2)
        result["remaining_seconds"] = max(0, int(target - elapsed))
        result["background_active"] = self._background_started
        result["stale"] = False
        result["requirements"] = {
            "elapsed_target_met": elapsed >= target,
            "sample_target_met": int(raw.get("sample_count") or 0) >= int(
                raw.get("min_samples") or self.min_samples
            ),
            "no_failures": int(raw.get("failure_count") or 0) == 0,
            "source_unchanged": raw.get("source_blobs") == self.source_blobs(),
            "sources_present": not self._missing_source_paths(),
            "max_gap_seconds": int(raw.get("max_gap_seconds") or self.max_gap_seconds),
        }
        return result

    def _missing_source_paths(self) -> list[str]:
        return [
            rel for rel in self.SOURCE_PATHS
            if not (self.root_dir / rel).is_file()
        ]

    def source_blobs(self) -> dict[str, str]:
        rows: dict[str, str] = {}
        for rel in self.SOURCE_PATHS:
            path = self.root_dir / rel
            if path.is_file():
                rows[rel] = self._git_blob_sha(path)
        return rows

    def _now(self) -> datetime:
        value = self.now_fn()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _read(self) -> dict[str, Any]:
        primary = self._read_path(self.state_path)
        if primary:
            return primary

        backup = self._read_path(self.backup_path)
        if not backup:
            return {}

        recovered = dict(backup)
        recovered["state_recovery"] = {
            "recovered_from_backup": True,
            "recovered_at": _iso(self._now()),
            "reason": (
                "primary_state_invalid"
                if self.state_path.exists()
                else "primary_state_missing"
            ),
        }
        # Restore the primary atomically without rotating a corrupt/missing
        # primary over the last known-good backup.
        self._write(recovered)
        return recovered

    @staticmethod
    def _read_path(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _write_json_atomically(path: Path, raw: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _write(self, raw: dict[str, Any]) -> None:
        current = self._read_path(self.state_path)
        if current:
            # Keep the previous verified-readable checkpoint. If the primary
            # is already corrupt, never overwrite the last known-good backup.
            self._write_json_atomically(self.backup_path, current)
        self._write_json_atomically(self.state_path, raw)

    @staticmethod
    def _git_blob_sha(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
        header = f"blob {len(normalized)}\0".encode("ascii")
        return sha1(header + normalized).hexdigest()
