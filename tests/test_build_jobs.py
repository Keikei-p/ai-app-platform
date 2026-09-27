import threading
import time
import unittest

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
        self.assertEqual(job.status, "queued")
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


if __name__ == "__main__":
    unittest.main()
