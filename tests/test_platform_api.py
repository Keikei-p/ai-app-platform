import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from src.core.platform_api import PlatformAPI


class FakeKnowledgeImportService:
    def __init__(self):
        self.import_id = "a" * 32
        self.pages = []

    def start_knowledge_import(self, name):
        return {
            "import_id": self.import_id,
            "name": name,
            "status": "active",
            "next_page": 0,
        }

    def ingest_knowledge_import_page(self, import_id, *, page_index, rows, final=False):
        if import_id != self.import_id:
            raise KeyError(import_id)
        self.pages.append((page_index, rows, final))
        return {
            "import_id": import_id,
            "status": "completed" if final else "active",
            "next_page": page_index + 1,
            "rows_received": len(rows),
        }

    def list_knowledge_imports(self, limit=50):
        return [{
            "import_id": self.import_id,
            "name": "docs",
            "status": "active",
        }][:limit]

    def knowledge_import(self, import_id):
        if import_id != self.import_id:
            raise KeyError(import_id)
        return {
            "import_id": import_id,
            "name": "docs",
            "status": "active",
        }


class PlatformAPITests(unittest.TestCase):
    def test_handler_is_constructible(self):
        api = PlatformAPI()
        handler = api.handler_class()
        self.assertTrue(issubclass(handler, object))
        self.assertGreaterEqual(len(api.csrf), 20)

    def test_knowledge_import_api_is_csrf_protected_and_resumable(self):
        service = FakeKnowledgeImportService()
        api = PlatformAPI(service=service)
        server = ThreadingHTTPServer(("127.0.0.1", 0), api.handler_class())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def request(method, path, payload=None, *, csrf=True):
            raw = None if payload is None else json.dumps(payload).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if csrf:
                headers["X-CSRF-Token"] = api.csrf
            req = urllib.request.Request(
                base + path,
                data=raw,
                headers=headers,
                method=method,
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))

        try:
            with patch.dict(os.environ, {"AI_APP_LOCAL_API_TOKEN": ""}, clear=False):
                with self.assertRaises(urllib.error.HTTPError) as blocked:
                    request(
                        "POST",
                        "/api/v1/knowledge/imports",
                        {"name": "docs"},
                        csrf=False,
                    )
                self.assertEqual(blocked.exception.code, 403)

                status, started = request(
                    "POST",
                    "/api/v1/knowledge/imports",
                    {"name": "docs"},
                )
                self.assertEqual(status, 201)
                self.assertEqual(started["import_id"], service.import_id)

                status, page = request(
                    "POST",
                    f"/api/v1/knowledge/imports/{service.import_id}/pages",
                    {
                        "page_index": 0,
                        "rows": [{
                            "topic": "Firebase",
                            "statement": "Authentication docs",
                            "sources": [{
                                "kind": "official_docs",
                                "locator": "https://example.com/firebase",
                                "content": "docs",
                            }],
                        }],
                        "final": True,
                    },
                )
                self.assertEqual(status, 200)
                self.assertEqual(page["status"], "completed")
                self.assertEqual(service.pages[0][0], 0)
                self.assertTrue(service.pages[0][2])

                status, listing = request("GET", "/api/v1/knowledge/imports")
                self.assertEqual(status, 200)
                self.assertEqual(listing["imports"][0]["import_id"], service.import_id)

                status, detail = request(
                    "GET",
                    f"/api/v1/knowledge/imports/{service.import_id}",
                )
                self.assertEqual(status, 200)
                self.assertEqual(detail["import_id"], service.import_id)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
