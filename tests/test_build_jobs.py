import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from src.core.build_jobs import BuildJobManager


class BuildJobManagerTests(unittest.TestCase):
    def test_reports_progress_and_completed_result(self):
        manager = BuildJobManager()
        finished = threading.Event()

        def runner(progress):
            progress("plan", "planning")
            progress("validate", "testing")
            finished.set()
            return {"ok": True, "message": "done"}

        job = manager.submit("demo", runner)
        self.assertIn(job.status, {"queued", "running", "completed"})
        self.assertTrue(finished.wait(2))
        for _ in range(50):
            row = manager.get(job.job_id)
            if row.status == "completed":
                break
            time.sleep(0.02)
        self.assertEqual(row.status, "completed")
        self.assertEqual(row.result["message"], "done")

    def test_failed_runner_is_captured_not_raised_from_worker(self):
        manager = BuildJobManager()

        def runner(progress):
            raise RuntimeError("boom")

        job = manager.submit("demo", runner)
        for _ in range(50):
            row = manager.get(job.job_id)
            if row.status == "failed":
                break
            time.sleep(0.02)
        self.assertEqual(row.status, "failed")
        self.assertIn("RuntimeError", row.error)

    def test_jobs_use_single_worker_to_avoid_project_write_races(self):
        manager = BuildJobManager()
        order = []
        first_release = threading.Event()

        def first(progress):
            order.append("first-start")
            first_release.wait(2)
            order.append("first-end")
            return {"ok": True}

        def second(progress):
            order.append("second-start")
            return {"ok": True}

        one = manager.submit("one", first)
        two = manager.submit("two", second)
        time.sleep(0.05)
        self.assertEqual(order, ["first-start"])
        first_release.set()
        for _ in range(100):
            if manager.get(two.job_id).status == "completed":
                break
            time.sleep(0.02)
        self.assertEqual(order, ["first-start", "first-end", "second-start"])


    def test_completed_job_history_survives_restart_without_raw_result(self):
        with tempfile.TemporaryDirectory() as td:
            history = Path(td) / "jobs.json"
            first = BuildJobManager(history_path=history)
            job = first.submit(
                "demo", lambda progress: {
                    "ok": True, "message": "done",
                    "source_code": "private code never persisted",
                }
            )
            for _ in range(100):
                if first.get(job.job_id).status == "completed":
                    break
                time.sleep(0.02)
            self.assertEqual(first.get(job.job_id).status, "completed")
            self.assertEqual(first.get(job.job_id).result["message"], "done")
            first._executor.shutdown(wait=True)
            restarted = BuildJobManager(history_path=history)
            saved = restarted.get(job.job_id)
            self.assertEqual(saved.status, "completed")
            self.assertEqual(saved.result, {"ok": True})
            self.assertNotIn("private code never persisted", history.read_text(encoding="utf-8"))
            self.assertTrue(restarted.watchdog_status()["persistence_ok"])

    def test_running_job_is_marked_interrupted_but_never_auto_retried(self):
        with tempfile.TemporaryDirectory() as td:
            history = Path(td) / "jobs.json"
            entered = threading.Event()
            release = threading.Event()
            executions = []

            def runner(progress):
                executions.append("started")
                entered.set()
                release.wait(3)
                return {"ok": True}

            original = BuildJobManager(history_path=history)
            job = original.submit("demo", runner)
            try:
                self.assertTrue(entered.wait(2))
                restarted = BuildJobManager(history_path=history)
                interrupted = restarted.get(job.job_id)
                self.assertEqual(interrupted.status, "failed")
                self.assertEqual(interrupted.stage, "interrupted")
                self.assertIn("new build approval", interrupted.message)
                self.assertEqual(restarted.watchdog_status()["interrupted_count"], 1)
                self.assertEqual(executions, ["started"])
                after_second_restart = BuildJobManager(history_path=history)
                self.assertEqual(after_second_restart.get(job.job_id).stage, "interrupted")
                self.assertEqual(executions, ["started"])
            finally:
                release.set()
                original._executor.shutdown(wait=True)

    def test_sensitive_results_and_exception_details_never_persist(self):
        with tempfile.TemporaryDirectory() as td:
            history = Path(td) / "jobs.json"
            secret = "sk-" + "X" * 32
            manager = BuildJobManager(history_path=history)

            def failed(progress):
                progress("planning", "token=" + secret)
                raise RuntimeError("token=" + secret)

            job = manager.submit("demo", failed)
            for _ in range(100):
                if manager.get(job.job_id).status == "failed":
                    break
                time.sleep(0.02)
            self.assertEqual(manager.get(job.job_id).status, "failed")
            self.assertIn(secret, manager.get(job.job_id).error)
            manager._executor.shutdown(wait=True)
            saved = history.read_text(encoding="utf-8")
            self.assertNotIn(secret, saved)
            self.assertNotIn("RuntimeError", saved)
            self.assertIn("Aivy build failed safely", saved)

    def test_corrupt_build_history_is_never_overwritten(self):
        for mode in ("primary", "both", "backup"):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as td:
                    history = Path(td) / "jobs.json"
                    backup = history.with_suffix(".json.bak")
                    original = BuildJobManager(history_path=history)
                    job = original.submit("demo", lambda p: {"ok": True})
                    for _ in range(100):
                        if original.get(job.job_id).status == "completed":
                            break
                        time.sleep(0.02)
                    original._executor.shutdown(wait=True)
                    if mode == "primary":
                        history.write_text("{invalid", encoding="utf-8")
                        # The valid backup remains available for recovery.
                    elif mode == "both":
                        history.write_text("{invalid", encoding="utf-8")
                        backup.write_text("{invalid backup", encoding="utf-8")
                    else:
                        backup.write_text("{invalid backup", encoding="utf-8")
                    before = {
                        p: p.read_bytes() for p in (history, backup) if p.exists()
                    }
                    restored = BuildJobManager(history_path=history)
                    if mode == "primary":
                        self.assertTrue(restored.watchdog_status()["persistence_ok"])
                        self.assertIsInstance(json.loads(history.read_text()), dict)
                    else:
                        self.assertFalse(restored.watchdog_status()["persistence_ok"])
                        with self.assertRaisesRegex(RuntimeError, "history requires recovery"):
                            restored.submit("demo", lambda p: {"ok": True})
                        self.assertEqual(
                            {p: p.read_bytes() for p in (history, backup) if p.exists()},
                            before,
                        )

    def test_watchdog_only_reports_stalled_jobs_and_never_retries(self):
        manager = BuildJobManager(stall_seconds=60)
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def runner(progress):
            calls.append(1)
            entered.set()
            release.wait(3)
            return {"ok": True}

        job = manager.submit("demo", runner)
        try:
            self.assertTrue(entered.wait(2))
            from datetime import datetime, timedelta, timezone
            with manager._lock:
                manager._jobs[job.job_id].updated_at = (
                    datetime.now(timezone.utc) - timedelta(minutes=3)
                ).isoformat()
            snapshot = manager.watchdog_status()
            self.assertEqual(snapshot["stalled_job_ids"], [job.job_id])
            self.assertEqual(snapshot["watchdog_actions"], "observation_only_no_auto_retry")
            self.assertEqual(calls, [1])
        finally:
            release.set()
            manager._executor.shutdown(wait=True)


if __name__ == "__main__":
    unittest.main()
