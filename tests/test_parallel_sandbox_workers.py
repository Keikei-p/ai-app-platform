import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from src.core.llm_chat import ChatProviderStatus
from src.core.model_router import ModelRouter
from src.core.parallel_sandbox_workers import ParallelSandboxWorkerPool


class FakeParallelEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def route_config(self, capability):
        return None

    def settings(self):
        return {"provider": "openai", "model": "fake-model", "routes": {}}

    def status(self, provider=None, model=None):
        return ChatProviderStatus(
            provider or "openai",
            model or "fake-model",
            True,
            "connected",
        )

    def reply_routed(self, provider, model, history, user_text, system_instruction):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.05)
            return json.dumps({
                "summary": "isolated review complete",
                "findings": ["snapshot inspected"],
                "recommendations": ["keep changes bounded"],
                "requested_tools": [],
                "uncertainties": [],
            })
        finally:
            with self.lock:
                self.active -= 1


class ParallelSandboxWorkerTests(unittest.TestCase):
    def test_workers_run_in_parallel_and_never_mutate_source(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            source = project / "app.py"
            source.write_text("print('original')\n", encoding="utf-8")
            secret = project / ".env"
            secret.write_text("SECRET=never-copy\n", encoding="utf-8")

            engine = FakeParallelEngine()
            pool = ParallelSandboxWorkerPool(
                engine=engine,
                router=ModelRouter(engine),
                sandbox_root=base / "sandboxes",
            )
            report = pool.run(
                goal="Review the app",
                project_slug="demo",
                project_dir=project,
                roles=("research", "architect", "test", "security"),
            )

            self.assertEqual(report.status, "completed")
            self.assertTrue(report.source_unchanged)
            self.assertEqual(source.read_text(encoding="utf-8"), "print('original')\n")
            self.assertGreaterEqual(engine.max_active, 2)
            self.assertEqual(len(report.workers), 4)
            self.assertTrue(all(row.file_count == 1 for row in report.workers))
            self.assertFalse((base / "sandboxes" / report.run_id).exists())
            history = project / report.history_path
            self.assertTrue(history.is_file())
            saved = json.loads(history.read_text(encoding="utf-8"))
            self.assertTrue(saved["source_unchanged"])
            self.assertEqual(len(saved["workers"]), 4)

    def test_unconnected_workers_finish_without_writing_source(self):
        class OfflineEngine(FakeParallelEngine):
            def status(self, provider=None, model=None):
                return ChatProviderStatus("none", "", False, "not connected")

            def settings(self):
                return {"provider": "none", "model": "", "routes": {}}

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            project = base / "project"
            project.mkdir()
            (project / "index.html").write_text("<h1>Aivy</h1>", encoding="utf-8")
            engine = OfflineEngine()
            pool = ParallelSandboxWorkerPool(
                engine=engine,
                router=ModelRouter(engine),
                sandbox_root=base / "sandboxes",
            )
            report = pool.run(
                goal="Review",
                project_slug="demo",
                project_dir=project,
                roles=("research", "security"),
            )
            self.assertEqual(report.status, "not_connected")
            self.assertTrue(report.source_unchanged)


if __name__ == "__main__":
    unittest.main()
