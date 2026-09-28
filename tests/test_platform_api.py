import http.client
import json
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

from src.core.platform_api import PlatformAPI


class FakeKnowledgeService:
    def __init__(self):
        self.calls = []

    def search_knowledge(self, query, *, verified_only=True, limit=8, minimum_confidence=0.0):
        self.calls.append(("search", query, verified_only, limit, minimum_confidence))
        return [{"knowledge": {"knowledge_id": "k1"}, "score": 0.9}]

    def knowledge_index_status(self):
        self.calls.append(("index",))
        return {"documents": 123, "fts": True, "search_mode": "sqlite_fts_plus_local_semantic"}

    def list_knowledge_imports(self, limit=50):
        self.calls.append(("list_imports", limit))
        return [{"import_id": "a" * 32, "status": "active"}]

    def knowledge_import(self, import_id):
        self.calls.append(("get_import", import_id))
        return {"import_id": import_id, "status": "active"}

    def start_knowledge_import(self, name):
        self.calls.append(("start_import", name))
        return {"import_id": "b" * 32, "name": name, "status": "active", "next_page": 0}

    def ingest_knowledge_batch(self, rows):
        self.calls.append(("batch", len(rows)))
        return {"accepted": len(rows), "rejected": 0}

    def ingest_knowledge_import_page(self, import_id, *, page_index, rows, final=False):
        self.calls.append(("page", import_id, page_index, len(rows), final))
        return {
            "import_id": import_id,
            "status": "completed" if final else "active",
            "next_page": page_index + 1,
            "accepted": len(rows),
        }

    def learning_status(self):
        self.calls.append(("learning_status",))
        return {
            "verified_examples": 3,
            "average_score": 96.0,
            "ai_backed_examples": 2,
            "training_stage": "collecting_verified_supervision",
        }

    def learning_examples(self, limit=50):
        self.calls.append(("learning_examples", limit))
        return [{"example_id": "verified-1", "evaluation_score": 97}]

    def learning_supervision_candidates(self, limit=100):
        self.calls.append(("learning_supervision", limit))
        return [{"messages": [{"role": "user", "content": "build"}]}]

    def list_missions(self, limit=100):
        self.calls.append(("list_missions", limit))
        return [{"mission_id": "m1", "status": "paused"}]

    def mission_detail(self, mission_id):
        self.calls.append(("mission_detail", mission_id))
        return {"mission_id": mission_id, "status": "paused"}

    def create_mission(self, *, goal, project_slug, max_cycles=8):
        self.calls.append(("create_mission", goal, project_slug, max_cycles))
        return {"mission_id": "m2", "status": "queued", "goal": goal, "project_slug": project_slug}

    def run_mission_cycle(self, mission_id, *, approved_build=False):
        self.calls.append(("run_mission", mission_id, approved_build))
        return {"mission_id": mission_id, "status": "running" if approved_build else "approval_required"}

    def pause_mission(self, mission_id):
        self.calls.append(("pause_mission", mission_id))
        return {"mission_id": mission_id, "status": "paused"}

    def cancel_mission(self, mission_id):
        self.calls.append(("cancel_mission", mission_id))
        return {"mission_id": mission_id, "status": "cancelled"}

    def run_parallel_sandbox_review(self, goal, project_slug, roles=None):
        self.calls.append(("parallel_sandbox", goal, project_slug, roles))
        return {
            "run_id": "sandbox-1",
            "status": "completed",
            "source_unchanged": True,
            "workers": [{"role": "security", "status": "completed"}],
        }

    def specialist_squad(self, goal, project_slug=None):
        self.calls.append(("specialist_squad", goal, project_slug))
        return {
            "goal": goal,
            "roles": ["coordinator", "architect", "coding", "test", "security", "mobile"],
            "worker_roles": ["architect", "coding", "test", "security", "mobile"],
            "reasons": {"mobile": ["matched: mobile"]},
            "scores": {"mobile": 80},
        }

    def task_graph_for(self, goal, project_slug=None):
        self.calls.append(("task_graph", goal, project_slug))
        return {
            "goal": goal,
            "nodes": [{"task_id": "inspect", "depends_on": []}],
            "waves": [["inspect"], ["generate"]],
        }

    def release_guardian_status(self, project_slug):
        self.calls.append(("release_guardian", project_slug))
        return {
            "status": "approval_required",
            "blockers": [],
            "warnings": [],
            "report_path": ".aiapp/reports/release_guardian.json",
        }

    def aivy_health_dashboard(self):
        self.calls.append(("health_dashboard",))
        return {
            "project_count": 2,
            "specialist_count": 15,
            "mission_count": 3,
            "active_missions": 1,
            "verified_learning_examples": 4,
            "average_learning_score": 95.0,
            "model_observations": 7,
            "status": "healthy",
        }

    def model_benchmark_summary(self, capability=None):
        self.calls.append(("model_benchmark", capability))
        return {
            "capability": capability,
            "observations": 2,
            "models": [{"provider": "openai", "model": "x", "success_rate": 1.0, "average_quality": 96.0}],
        }

    def project_memory(self, project_slug, limit=100):
        self.calls.append(("project_memory", project_slug, limit))
        return [{"category": "verified_build", "statement": "works"}]

    def dependency_health(self, project_slug):
        self.calls.append(("dependency_health", project_slug))
        return {"status": "pass", "dependency_count": 2, "findings": []}

    def compare_candidate_arena(self, baseline, candidates):
        self.calls.append(("candidate_arena", len(candidates)))
        return {
            "status": "human_review_required",
            "winner_id": "candidate-a",
            "baseline_score": baseline.get("score", 0),
            "candidates": [],
            "auto_apply": False,
        }


class PlatformAPITests(unittest.TestCase):
    def test_handler_is_constructible(self):
        api = PlatformAPI()
        handler = api.handler_class()
        self.assertTrue(issubclass(handler, object))
        self.assertGreaterEqual(len(api.csrf), 20)

    def _server(self):
        service = FakeKnowledgeService()
        api = PlatformAPI(service)
        server = ThreadingHTTPServer(("127.0.0.1", 0), api.handler_class())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        deadline = time.time() + 1.0
        while not thread.is_alive() and time.time() < deadline:
            time.sleep(0.005)
        if not thread.is_alive():
            server.server_close()
            raise RuntimeError("test API server did not start")
        time.sleep(0.01)
        return api, service, server, thread

    @staticmethod
    def _request(server, method, path, *, body=None, headers=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            server.server_address[1],
            timeout=5,
        )
        payload = None
        request_headers = dict(headers or {})
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
            request_headers["Content-Length"] = str(len(payload))
        connection.request(method, path, body=payload, headers=request_headers)
        response = connection.getresponse()
        raw = response.read()
        data = json.loads(raw.decode("utf-8"))
        connection.close()
        return response.status, data

    def test_knowledge_search_index_and_import_routes(self):
        api, service, server, thread = self._server()
        try:
            status, data = self._request(
                server,
                "GET",
                "/api/v1/knowledge/search?q=Firebase%20auth&limit=4&minimum_confidence=0.5",
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["results"][0]["knowledge"]["knowledge_id"], "k1")
            self.assertEqual(service.calls[-1], ("search", "Firebase auth", True, 4, 0.5))

            status, data = self._request(server, "GET", "/api/v1/knowledge/index")
            self.assertEqual(status, 200)
            self.assertEqual(data["documents"], 123)

            status, data = self._request(
                server,
                "GET",
                "/api/v1/knowledge/imports?limit=7",
            )
            self.assertEqual(status, 200)
            self.assertEqual(service.calls[-1], ("list_imports", 7))

            import_id = "a" * 32
            status, data = self._request(
                server,
                "GET",
                f"/api/v1/knowledge/imports/{import_id}",
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["import_id"], import_id)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_learning_routes_expose_verified_growth_state(self):
        api, service, server, thread = self._server()
        try:
            status, data = self._request(server, "GET", "/api/v1/learning/status")
            self.assertEqual(status, 200)
            self.assertEqual(data["verified_examples"], 3)
            self.assertEqual(service.calls[-1], ("learning_status",))

            status, data = self._request(server, "GET", "/api/v1/learning/examples?limit=7")
            self.assertEqual(status, 200)
            self.assertEqual(data["examples"][0]["example_id"], "verified-1")
            self.assertEqual(service.calls[-1], ("learning_examples", 7))

            status, data = self._request(server, "GET", "/api/v1/learning/supervision?limit=9")
            self.assertEqual(status, 200)
            self.assertEqual(len(data["candidates"]), 1)
            self.assertEqual(service.calls[-1], ("learning_supervision", 9))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_health_memory_dependency_benchmark_and_arena_routes(self):
        api, service, server, thread = self._server()
        try:
            status, data = self._request(server, "GET", "/api/v1/health/dashboard")
            self.assertEqual(status, 200)
            self.assertEqual(data["specialist_count"], 15)
            self.assertEqual(service.calls[-1], ("health_dashboard",))

            status, data = self._request(
                server, "GET", "/api/v1/models/benchmark?capability=coding"
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["observations"], 2)
            self.assertEqual(service.calls[-1], ("model_benchmark", "coding"))

            status, data = self._request(
                server, "GET", "/api/v1/projects/demo/memory?limit=6"
            )
            self.assertEqual(status, 200)
            self.assertEqual(len(data["memory"]), 1)
            self.assertEqual(service.calls[-1], ("project_memory", "demo", 6))

            status, data = self._request(
                server, "GET", "/api/v1/projects/demo/dependency-health"
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["status"], "pass")

            status, _ = self._request(
                server,
                "POST",
                "/api/v1/arena/compare",
                body={"baseline": {"score": 80}, "candidates": {"candidate-a": {"score": 90}}},
            )
            self.assertEqual(status, 403)

            headers = {"X-CSRF-Token": api.csrf}
            status, data = self._request(
                server,
                "POST",
                "/api/v1/arena/compare",
                body={"baseline": {"score": 80}, "candidates": {"candidate-a": {"score": 90}}},
                headers=headers,
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["winner_id"], "candidate-a")
            self.assertFalse(data["auto_apply"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_mission_control_routes_persist_and_require_csrf(self):
        api, service, server, thread = self._server()
        try:
            status, data = self._request(server, "GET", "/api/v1/missions?limit=7")
            self.assertEqual(status, 200)
            self.assertEqual(data["missions"][0]["mission_id"], "m1")
            self.assertEqual(service.calls[-1], ("list_missions", 7))

            status, data = self._request(server, "GET", "/api/v1/missions/m1")
            self.assertEqual(status, 200)
            self.assertEqual(data["mission_id"], "m1")

            status, _ = self._request(
                server,
                "POST",
                "/api/v1/missions",
                body={"goal": "Improve app", "project_slug": "demo"},
            )
            self.assertEqual(status, 403)

            headers = {"X-CSRF-Token": api.csrf}
            status, data = self._request(
                server,
                "POST",
                "/api/v1/missions",
                body={"goal": "Improve app", "project_slug": "demo", "max_cycles": 6},
                headers=headers,
            )
            self.assertEqual(status, 201)
            self.assertEqual(data["status"], "queued")
            self.assertEqual(service.calls[-1], ("create_mission", "Improve app", "demo", 6))

            status, data = self._request(
                server,
                "POST",
                "/api/v1/missions/m2/run",
                body={"approved_build": False},
                headers=headers,
            )
            self.assertEqual(status, 202)
            self.assertEqual(data["status"], "approval_required")

            status, data = self._request(
                server,
                "POST",
                "/api/v1/missions/m2/run",
                body={"approved_build": True},
                headers=headers,
            )
            self.assertEqual(status, 202)
            self.assertEqual(data["status"], "running")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_specialist_squad_route_requires_csrf(self):
        api, service, server, thread = self._server()
        try:
            status, _ = self._request(
                server,
                "POST",
                "/api/v1/agent/squad",
                body={"goal": "mobile app", "project_slug": "demo"},
            )
            self.assertEqual(status, 403)

            headers = {"X-CSRF-Token": api.csrf}
            status, data = self._request(
                server,
                "POST",
                "/api/v1/agent/squad",
                body={"goal": "mobile app", "project_slug": "demo"},
                headers=headers,
            )
            self.assertEqual(status, 200)
            self.assertIn("mobile", data["roles"])
            self.assertEqual(
                service.calls[-1],
                ("specialist_squad", "mobile app", "demo"),
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_task_graph_and_release_guardian_routes(self):
        api, service, server, thread = self._server()
        try:
            headers = {"X-CSRF-Token": api.csrf}

            status, data = self._request(
                server,
                "POST",
                "/api/v1/agent/task-graph",
                body={"goal": "Build web app", "project_slug": "demo"},
                headers=headers,
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["waves"][0], ["inspect"])
            self.assertEqual(service.calls[-1], ("task_graph", "Build web app", "demo"))

            status, _ = self._request(
                server,
                "POST",
                "/api/v1/projects/demo/release-guardian",
                body={},
            )
            self.assertEqual(status, 403)

            status, data = self._request(
                server,
                "POST",
                "/api/v1/projects/demo/release-guardian",
                body={},
                headers=headers,
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["status"], "approval_required")
            self.assertEqual(service.calls[-1], ("release_guardian", "demo"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_parallel_sandbox_route_requires_csrf(self):
        api, service, server, thread = self._server()
        try:
            status, _ = self._request(
                server,
                "POST",
                "/api/v1/agent/sandbox/parallel",
                body={"goal": "Review", "project_slug": "demo"},
            )
            self.assertEqual(status, 403)

            headers = {"X-CSRF-Token": api.csrf}
            status, data = self._request(
                server,
                "POST",
                "/api/v1/agent/sandbox/parallel",
                body={
                    "goal": "Review",
                    "project_slug": "demo",
                    "roles": ["security", "test"],
                },
                headers=headers,
            )
            self.assertEqual(status, 200)
            self.assertTrue(data["source_unchanged"])
            self.assertEqual(
                service.calls[-1],
                ("parallel_sandbox", "Review", "demo", ("security", "test")),
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_mutating_knowledge_routes_require_csrf_and_accept_paged_import(self):
        api, service, server, thread = self._server()
        try:
            status, _ = self._request(
                server,
                "POST",
                "/api/v1/knowledge/imports",
                body={"name": "docs"},
            )
            self.assertEqual(status, 403)

            headers = {"X-CSRF-Token": api.csrf}
            status, data = self._request(
                server,
                "POST",
                "/api/v1/knowledge/imports",
                body={"name": "docs"},
                headers=headers,
            )
            self.assertEqual(status, 201)
            import_id = data["import_id"]

            row = {
                "topic": "Firebase",
                "statement": "Authentication pattern",
                "sources": [{
                    "kind": "official_docs",
                    "locator": "https://example.com/firebase",
                    "content": "Public documentation.",
                }],
            }
            status, data = self._request(
                server,
                "POST",
                f"/api/v1/knowledge/imports/{import_id}/pages",
                body={"page_index": 0, "rows": [row], "final": True},
                headers=headers,
            )
            self.assertEqual(status, 200)
            self.assertEqual(data["status"], "completed")
            self.assertEqual(service.calls[-1], ("page", import_id, 0, 1, True))

            status, data = self._request(
                server,
                "POST",
                "/api/v1/knowledge/batch",
                body={"rows": [row]},
                headers=headers,
            )
            self.assertEqual(status, 202)
            self.assertEqual(data["accepted"], 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
