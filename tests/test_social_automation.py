import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.generator import StarterGenerator
from src.core.planner import IntentPlanner
from src.core.social_generator import SocialAutomationGenerator
from src.core.test_runner import ProjectTestRunner


class SocialPlannerTests(unittest.TestCase):
    def test_sns_request_selects_social_automation(self):
        plan = IntentPlanner().plan(
            "SNS Bot",
            "sns-bot",
            "ThreadsとInstagramとYouTubeへ予約して自動投稿するSNS管理アプリを作りたい",
        )
        self.assertEqual(plan.spec.app_type, "social_automation")
        self.assertIn("scheduler", plan.spec.features)
        self.assertIn("social_publish", plan.spec.features)


class SocialGeneratedRuntimeTests(unittest.TestCase):
    def _generate(self, root: Path):
        (root / "project.json").write_text(
            '{"name":"SNS Bot","slug":"sns-bot"}',
            encoding="utf-8",
        )
        spec = AppSpec(
            "SNS Bot",
            "sns-bot",
            "SNS自動投稿",
            "social_automation",
            ["scheduler", "social_publish"],
            ["web"],
        )
        spec.save(root)
        StarterGenerator().generate_from_spec(root, spec)
        SocialAutomationGenerator().generate(root, spec)
        return spec

    def _load_runtime(self, root: Path):
        path = root / "social_runtime.py"
        spec = importlib.util.spec_from_file_location("generated_social_runtime_test", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_generated_project_passes_structure_checks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._generate(root)
            results = ProjectTestRunner().run(root)
            failed = [x for x in results if not x.passed]
            self.assertEqual(failed, [], failed)

    def test_manual_approval_then_dry_run_posts(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._generate(root)
            runtime = self._load_runtime(root)
            store = runtime.SocialStore(root / "queue.db")
            self.assertFalse(store.auto_mode())
            post = store.enqueue("threads", "hello", scheduled_at=runtime.utc_ts() - 1)
            self.assertEqual(post["status"], "pending_approval")
            self.assertTrue(store.approve(post["id"]))
            result = runtime.run_once(store)
            self.assertTrue(result["ok"])
            saved = store.list_posts()[0]
            self.assertEqual(saved["status"], "posted")
            self.assertTrue(saved["remote_id"].startswith("dryrun-"))

    def test_auto_mode_queues_without_manual_approval(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._generate(root)
            runtime = self._load_runtime(root)
            store = runtime.SocialStore(root / "queue.db")
            store.set_auto_mode(True)
            post = store.enqueue("x", "auto", scheduled_at=runtime.utc_ts() - 1)
            self.assertEqual(post["status"], "queued")
            result = runtime.run_once(store)
            self.assertTrue(result["ok"])
            self.assertEqual(store.list_posts()[0]["status"], "posted")

    def test_idempotency_key_prevents_duplicate_queue_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._generate(root)
            runtime = self._load_runtime(root)
            store = runtime.SocialStore(root / "queue.db")
            first = store.enqueue("threads", "same", idempotency_key="same-key")
            second = store.enqueue("threads", "same", idempotency_key="same-key")
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(len(store.list_posts()), 1)

    def test_provider_failure_enters_retry_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._generate(root)
            runtime = self._load_runtime(root)
            store = runtime.SocialStore(root / "queue.db")
            store.set_auto_mode(True)
            post = store.enqueue("threads", "will fail", scheduled_at=runtime.utc_ts() - 1)

            class FailingProvider:
                def publish(self, _post):
                    raise RuntimeError("provider unavailable")

            runtime.provider_for = lambda _platform: FailingProvider()
            result = runtime.run_once(store)
            self.assertFalse(result["ok"])
            saved = next(x for x in store.list_posts() if x["id"] == post["id"])
            self.assertEqual(saved["status"], "retry")
            self.assertEqual(saved["attempts"], 1)
            self.assertIn("provider unavailable", saved["last_error"])

    def test_youtube_media_path_cannot_escape_media_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._generate(root)
            runtime = self._load_runtime(root)
            outside = root / "outside.mp4"
            outside.write_bytes(b"video")
            old_root = runtime.MEDIA_ROOT
            runtime.MEDIA_ROOT = root / "media"
            try:
                with self.assertRaises(RuntimeError):
                    runtime._safe_media_path("../outside.mp4")
            finally:
                runtime.MEDIA_ROOT = old_root

    def test_credential_status_does_not_return_secret_values(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._generate(root)
            runtime = self._load_runtime(root)
            previous = os.environ.get("X_ACCESS_TOKEN")
            try:
                os.environ["X_ACCESS_TOKEN"] = "super-secret-token-value"
                status = runtime.credential_status()
                self.assertTrue(status["x"])
                self.assertNotIn("super-secret-token-value", repr(status))
            finally:
                if previous is None:
                    os.environ.pop("X_ACCESS_TOKEN", None)
                else:
                    os.environ["X_ACCESS_TOKEN"] = previous


if __name__ == "__main__":
    unittest.main()
