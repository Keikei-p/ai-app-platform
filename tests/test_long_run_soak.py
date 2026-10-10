from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.config import ROOT_DIR
from src.core.long_run_soak import LongRunSoakMonitor


class FakeClock:
    def __init__(self):
        self.value = datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)

    def now(self):
        return self.value

    def advance(self, seconds: int):
        self.value += timedelta(seconds=seconds)


def healthy_callbacks():
    return {
        "self_drive_status": lambda: {
            "enabled": True,
            "background_active": True,
            "approval_bypass_allowed": False,
        },
        "daily_evolution_status": lambda: {
            "enabled": True,
            "background_active": True,
            "source_self_edit_allowed": False,
        },
        "strategic_status": lambda: {
            "active_goals": 1,
            "waiting_on_mission": 0,
            "build_auto_approval": False,
        },
        "health_status": lambda: {"status": "healthy"},
    }


class LongRunSoakTests(unittest.TestCase):
    def make_monitor(self, root: Path, clock: FakeClock, **overrides):
        callbacks = healthy_callbacks()
        callbacks.update(overrides)
        return LongRunSoakMonitor(
            **callbacks,
            root_dir=ROOT_DIR,
            state_path=root / "soak.json",
            now_fn=clock.now,
            target_seconds=3600,
            heartbeat_seconds=900,
            max_gap_seconds=1200,
            min_samples=5,
        )

    def test_fake_clock_proves_logic_but_requires_all_duration_and_samples(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = FakeClock()
            monitor = self.make_monitor(root, clock)
            monitor.start(reset=True)

            first = monitor.checkpoint(trigger="test")
            self.assertFalse(first["verified"])
            self.assertEqual(first["sample_count"], 1)

            for _ in range(4):
                clock.advance(900)
                row = monitor.checkpoint(trigger="test")

            self.assertTrue(row["verified"])
            self.assertEqual(row["status"], "verified")
            self.assertEqual(row["sample_count"], 5)
            self.assertEqual(row["failure_count"], 0)
            self.assertTrue(row["requirements"]["elapsed_target_met"])
            self.assertTrue(row["requirements"]["sample_target_met"])
            self.assertTrue(row["requirements"]["no_failures"])

    def test_large_monitoring_gap_restarts_window_instead_of_cheating_duration(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = FakeClock()
            monitor = self.make_monitor(root, clock)
            monitor.start(reset=True)
            monitor.checkpoint(trigger="test")
            clock.advance(1800)

            row = monitor.checkpoint(trigger="test")

            self.assertFalse(row["verified"])
            self.assertEqual(row["sample_count"], 1)
            self.assertEqual(row["elapsed_seconds"], 0)
            self.assertIn("monitoring gap", row.get("restart_reason", ""))

    def test_background_poll_keeps_cadence_without_redundant_writes(self):
        with TemporaryDirectory() as tmp:
            clock = FakeClock()
            monitor = self.make_monitor(Path(tmp), clock)
            monitor.ensure_active()
            self.assertTrue(monitor.background_poll_once())
            original = (Path(tmp) / "soak.json").read_bytes()
            self.assertFalse(monitor.background_poll_once())
            self.assertEqual((Path(tmp) / "soak.json").read_bytes(), original)
            clock.advance(60)
            self.assertFalse(monitor.background_poll_once())
            self.assertEqual(monitor.status()["sample_count"], 1)
            clock.advance(840)
            self.assertTrue(monitor.background_poll_once())
            self.assertEqual(monitor.status()["sample_count"], 2)

    def test_sleep_gap_is_stale_before_first_resume_checkpoint(self):
        with TemporaryDirectory() as tmp:
            clock = FakeClock()
            monitor = self.make_monitor(Path(tmp), clock)
            first = monitor.start(reset=True)
            monitor.checkpoint(trigger="before_sleep")
            clock.advance(1800)

            stale = monitor.status()
            self.assertEqual(stale["status"], "stale")
            self.assertFalse(stale["verified"])
            self.assertTrue(stale["requires_checkpoint"])
            self.assertIn("monitoring gap", stale["reason"])
            self.assertEqual(stale["session_id"], first["session_id"])

            self.assertTrue(monitor.background_poll_once())
            resumed = monitor.status()
            self.assertEqual(resumed["status"], "running")
            self.assertFalse(resumed["verified"])
            self.assertNotEqual(resumed["session_id"], first["session_id"])
            self.assertEqual(resumed["sample_count"], 1)
            self.assertIn("monitoring gap", resumed["restart_reason"])

    def test_background_poll_after_restart_respects_last_checkpoint(self):
        with TemporaryDirectory() as tmp:
            clock = FakeClock()
            old = self.make_monitor(Path(tmp), clock)
            old.start(reset=True)
            old.checkpoint(trigger="first")
            clock.advance(600)
            restarted = self.make_monitor(Path(tmp), clock)
            restarted.ensure_active()
            self.assertFalse(restarted.background_poll_once())
            self.assertEqual(restarted.status()["sample_count"], 1)
            clock.advance(300)
            self.assertTrue(restarted.background_poll_once())
            self.assertEqual(restarted.status()["sample_count"], 2)

    def test_verified_soak_is_not_rewritten_on_idle_poll(self):
        with TemporaryDirectory() as tmp:
            clock = FakeClock()
            monitor = self.make_monitor(Path(tmp), clock)
            monitor.start(reset=True)
            for index in range(5):
                if index:
                    clock.advance(900)
                verified = monitor.checkpoint(trigger="test")
            self.assertTrue(verified["verified"])
            saved = (Path(tmp) / "soak.json").read_bytes()
            clock.advance(1800)
            self.assertFalse(monitor.background_poll_once())
            self.assertEqual(monitor.status()["status"], "verified")
            self.assertEqual((Path(tmp) / "soak.json").read_bytes(), saved)

    def test_background_poll_detects_clock_rollback(self):
        with TemporaryDirectory() as tmp:
            clock = FakeClock()
            monitor = self.make_monitor(Path(tmp), clock)
            monitor.start(reset=True)
            first = monitor.checkpoint(trigger="before_rollback")
            clock.advance(-60)
            self.assertTrue(monitor.background_poll_once())
            fresh = monitor.status()
            self.assertNotEqual(first["session_id"], fresh["session_id"])
            self.assertFalse(fresh["verified"])
            self.assertIn("clock moved backwards", fresh["restart_reason"])

    def test_restart_within_gap_preserves_real_soak_window(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = FakeClock()
            first_monitor = self.make_monitor(root, clock)
            first_monitor.start(reset=True)
            first = first_monitor.checkpoint(trigger="before_restart")
            self.assertEqual(first["sample_count"], 1)

            clock.advance(900)
            restarted_monitor = self.make_monitor(root, clock)
            active = restarted_monitor.ensure_active()
            self.assertEqual(active["session_id"], first["session_id"])

            second = restarted_monitor.checkpoint(trigger="after_restart")
            self.assertFalse(second["verified"])
            self.assertEqual(second["session_id"], first["session_id"])
            self.assertEqual(second["sample_count"], 2)
            self.assertEqual(second["elapsed_seconds"], 900)
            self.assertEqual(second["failure_count"], 0)

    def test_restart_after_excessive_gap_resets_soak_window(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = FakeClock()
            first_monitor = self.make_monitor(root, clock)
            first_monitor.start(reset=True)
            first = first_monitor.checkpoint(trigger="before_restart")

            clock.advance(1800)
            restarted_monitor = self.make_monitor(root, clock)
            second = restarted_monitor.checkpoint(trigger="after_restart")

            self.assertFalse(second["verified"])
            self.assertNotEqual(second["session_id"], first["session_id"])
            self.assertEqual(second["sample_count"], 1)
            self.assertEqual(second["elapsed_seconds"], 0)
            self.assertIn("monitoring gap", second.get("restart_reason", ""))

    def test_corrupt_primary_recovers_last_known_good_checkpoint(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = FakeClock()
            monitor = self.make_monitor(root, clock)
            started = monitor.start(reset=True)
            first = monitor.checkpoint(trigger="first")
            clock.advance(900)
            second = monitor.checkpoint(trigger="second")

            self.assertEqual(second["sample_count"], 2)
            self.assertTrue((root / "soak.json.bak").is_file())

            (root / "soak.json").write_text("{broken-json", encoding="utf-8")
            restarted = self.make_monitor(root, clock)
            recovered = restarted.ensure_active()

            self.assertEqual(recovered["session_id"], started["session_id"])
            self.assertEqual(recovered["sample_count"], first["sample_count"])
            self.assertTrue(recovered["state_recovery"]["recovered_from_backup"])
            self.assertEqual(
                recovered["state_recovery"]["reason"],
                "primary_state_invalid",
            )

            persisted = (root / "soak.json").read_text(encoding="utf-8")
            self.assertIn('"recovered_from_backup": true', persisted)

            # Startup recovery is immediately followed by the monitor's first
            # checkpoint, so the restored heartbeat remains inside the gap budget.
            resumed = restarted.checkpoint(trigger="after_recovery")
            self.assertEqual(resumed["session_id"], started["session_id"])
            self.assertEqual(resumed["sample_count"], 2)

    def test_corrupt_primary_and_backup_block_writes_without_erasing_evidence(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = FakeClock()
            monitor = self.make_monitor(root, clock)
            monitor.start(reset=True)
            monitor.checkpoint(trigger="first")
            clock.advance(900)
            monitor.checkpoint(trigger="second")

            primary = root / "soak.json"
            backup = root / "soak.json.bak"
            primary.write_bytes(b"{broken-primary")
            backup.write_bytes(b"{broken-backup")
            before = (primary.read_bytes(), backup.read_bytes())

            restarted = self.make_monitor(root, clock)
            with self.assertRaisesRegex(RuntimeError, "Soak evidence is blocked"):
                restarted.ensure_active()
            with self.assertRaisesRegex(RuntimeError, "Soak evidence is blocked"):
                restarted.checkpoint(trigger="restarted")
            blocked = restarted.status()
            self.assertEqual(blocked["status"], "blocked")
            self.assertFalse(blocked["verified"])
            self.assertEqual(blocked["storage_issue"], "unrecoverable_evidence_files")
            self.assertEqual((primary.read_bytes(), backup.read_bytes()), before)
            # An unreadable audit file must not prevent the Ivy service from
            # starting; the background monitor can report a blocked condition.
            self.assertTrue(restarted.start_background())
            self.assertEqual(restarted.status()["status"], "blocked")
            self.assertEqual((primary.read_bytes(), backup.read_bytes()), before)

    def test_unreadable_backup_blocks_verified_claim_and_preserves_both_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = FakeClock()
            monitor = self.make_monitor(root, clock)
            monitor.start(reset=True)
            monitor.checkpoint(trigger="first")
            for _ in range(4):
                clock.advance(900)
                verified = monitor.checkpoint(trigger="next")
            self.assertTrue(verified["verified"])

            primary = root / "soak.json"
            backup = root / "soak.json.bak"
            backup.write_bytes(b"{broken-backup")
            before = (primary.read_bytes(), backup.read_bytes())

            self.assertEqual(monitor.status()["status"], "blocked")
            self.assertFalse(monitor.status()["verified"])
            self.assertEqual(
                monitor.status()["storage_issue"], "unreadable_evidence_backup"
            )
            with self.assertRaisesRegex(RuntimeError, "Soak evidence is blocked"):
                monitor.checkpoint(trigger="do_not_reuse_verification")
            self.assertEqual((primary.read_bytes(), backup.read_bytes()), before)

    def test_unreadable_backup_only_never_becomes_fresh_install(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = FakeClock()
            backup = root / "soak.json.bak"
            backup.write_bytes(b"{unrecoverable-backup")
            monitor = self.make_monitor(root, clock)
            with self.assertRaisesRegex(RuntimeError, "Soak evidence is blocked"):
                monitor.start(reset=True)
            with self.assertRaisesRegex(RuntimeError, "Soak evidence is blocked"):
                monitor.ensure_active()
            self.assertFalse((root / "soak.json").exists())
            self.assertEqual(backup.read_bytes(), b"{unrecoverable-backup")
            self.assertEqual(monitor.status()["status"], "blocked")

    def test_runtime_failure_prevents_verification(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = FakeClock()
            callbacks = healthy_callbacks()
            callbacks["health_status"] = lambda: {"status": "critical"}
            monitor = self.make_monitor(root, clock, **callbacks)
            monitor.start(reset=True)

            for i in range(5):
                if i:
                    clock.advance(900)
                row = monitor.checkpoint(trigger="test")

            self.assertFalse(row["verified"])
            self.assertGreater(row["failure_count"], 0)
            self.assertFalse(row["requirements"]["no_failures"])
            self.assertIn("health_critical", row["last_failure"]["reasons"])

    def test_protected_boundaries_are_part_of_each_sample(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = FakeClock()
            callbacks = healthy_callbacks()
            callbacks["strategic_status"] = lambda: {
                "build_auto_approval": True,
            }
            monitor = self.make_monitor(root, clock, **callbacks)
            monitor.start(reset=True)
            row = monitor.checkpoint(trigger="test")

            self.assertFalse(row["samples"][-1]["ok"])
            self.assertIn(
                "strategy_auto_approval_boundary_invalid",
                row["samples"][-1]["reasons"],
            )

    def test_backward_clock_invalidates_soak_evidence_before_checkpoint(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = FakeClock()
            monitor = self.make_monitor(root, clock)
            old = monitor.start(reset=True)
            monitor.checkpoint(trigger="first")
            clock.advance(900)
            monitor.checkpoint(trigger="second")
            clock.advance(-1000)

            stale = monitor.status()
            self.assertFalse(stale["verified"])
            self.assertEqual(stale["status"], "stale")
            self.assertIn("clock moved backwards", stale["reason"])

            fresh = monitor.checkpoint(trigger="after_clock_rollback")
            self.assertNotEqual(fresh["session_id"], old["session_id"])
            self.assertEqual(fresh["sample_count"], 1)
            self.assertEqual(fresh["elapsed_seconds"], 0)
            self.assertFalse(fresh["verified"])
            self.assertIn("clock moved backwards", fresh["restart_reason"])

    def test_missing_covered_source_cannot_pass_even_with_duration_and_samples(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = FakeClock()
            monitor = LongRunSoakMonitor(
                **healthy_callbacks(),
                root_dir=root / "missing_source_checkout",
                state_path=root / "soak.json",
                now_fn=clock.now,
                target_seconds=3600,
                heartbeat_seconds=900,
                max_gap_seconds=1200,
                min_samples=5,
            )
            monitor.start(reset=True)
            for index in range(5):
                if index:
                    clock.advance(900)
                result = monitor.checkpoint(trigger="test")

            self.assertTrue(result["requirements"]["elapsed_target_met"])
            self.assertTrue(result["requirements"]["sample_target_met"])
            self.assertFalse(result["requirements"]["sources_present"])
            self.assertFalse(result["verified"])
            self.assertIn("covered_source_missing", result["last_failure"]["reasons"])
            stale = monitor.status()
            self.assertEqual(stale["status"], "stale")
            self.assertFalse(stale["verified"])

    def test_default_contract_is_real_24h_not_short_simulation(self):
        callbacks = healthy_callbacks()
        with TemporaryDirectory() as tmp:
            monitor = LongRunSoakMonitor(
                **callbacks,
                root_dir=ROOT_DIR,
                state_path=Path(tmp) / "soak.json",
            )
            self.assertEqual(monitor.target_seconds, 24 * 60 * 60)
            self.assertEqual(monitor.heartbeat_seconds, 15 * 60)
            self.assertEqual(monitor.max_gap_seconds, 45 * 60)
            self.assertGreaterEqual(monitor.min_samples, 80)


if __name__ == "__main__":
    unittest.main()
