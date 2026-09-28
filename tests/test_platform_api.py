import http.client
import json
import threading
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
