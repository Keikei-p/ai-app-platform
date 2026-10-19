"""Contract tests: stand-alone Ivy Server and opt-in AI COMPANY OS bridge."""
from __future__ import annotations

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
import json
import os
import socket
import unittest

from src.core.company_bridge import CompanyBridge
from src.core.platform_api import PlatformAPI, serve


TOKEN = "ivy-company-test-token-" + ("X" * 32)


class FakeCompanyMissionService:
    def __init__(self):
        self.calls = []

    def build_watchdog_status(self):
        return {"active_count": 2, "persistence_ok": True,
                "persistence_issue": None}

    def create_mission(self, *, goal, project_slug, max_cycles):
        self.calls.append((goal, project_slug, max_cycles))
        if project_slug == "missing":
            raise FileNotFoundError("private user path")
        return {"mission_id": "mission-123", "status": "queued",
                "goal": goal, "private_path": "SECRET"}


class CompanyBridgeContractTests(unittest.TestCase):
    def test_token_disabled_by_default_and_rejects_remote_network(self):
        s = FakeCompanyMissionService()
        bridge = CompanyBridge(s, env={})
        self.assertFalse(bridge.authorized("127.0.0.1", TOKEN))
        bridge = CompanyBridge(s, env={"AIVY_COMPANY_BRIDGE_TOKEN": TOKEN})
        self.assertTrue(bridge.authorized("127.0.0.1", TOKEN))
        self.assertTrue(bridge.authorized("::1", TOKEN))
        self.assertFalse(bridge.authorized("127.0.0.1", TOKEN + "bad"))
        self.assertFalse(bridge.authorized("192.168.1.12", TOKEN))
        self.assertFalse(bridge.authorized("127.0.0.1", TOKEN, remote_mode=True))
        self.assertFalse(CompanyBridge(s, env={"AIVY_COMPANY_BRIDGE_TOKEN": "short"}).enabled)

    def test_enqueued_only_planning_never_runs_build_or_exposes_secret(self):
        fake = FakeCompanyMissionService()
        bridge = CompanyBridge(fake, env={"AIVY_COMPANY_BRIDGE_TOKEN": TOKEN})
        out = bridge.enqueue_mission({
            "goal": "  build an app ", "project_slug": "demo", "max_cycles": 2
        })
        self.assertEqual(fake.calls, [("build an app", "demo", 2)])
        self.assertEqual(out["status"], "queued")
        self.assertTrue(out["requires_owner_approval"])
        self.assertFalse(out["executed"])
        self.assertFalse(out["publish_performed"])
        self.assertNotIn("SECRET", str(out))
        self.assertNotIn("build an app", str(out))
        status = bridge.status()
        self.assertNotIn(TOKEN, str(status))
        self.assertEqual(status["active_build_count"], 2)
        self.assertFalse(status["automatic_build_approval"])

    def test_rejects_approvals_unknown_fields_and_invalid_missions(self):
        fake = FakeCompanyMissionService()
        bridge = CompanyBridge(fake, env={"AIVY_COMPANY_BRIDGE_TOKEN": TOKEN})
        requests = [
            {"goal": "X", "project_slug": "demo", "approved_build": True},
            {"goal": "X", "project_slug": "demo", "max_cycles": True},
            {"goal": "X", "project_slug": "../secrets"},
            {"goal": "", "project_slug": "demo"},
            {"goal": "X", "project_slug": "demo", "max_cycles": 100},
            {"goal": "X", "project_slug": "demo", "shell": "powershell"},
        ]
        for body in requests:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    bridge.enqueue_mission(body)
        self.assertEqual(fake.calls, [])

    def _server(self, *, with_token=True, remote_mode=False):
        fake = FakeCompanyMissionService()
        values = {"AIVY_COMPANY_BRIDGE_TOKEN": TOKEN} if with_token else {}
        with patch.dict(os.environ, values, clear=True):
            api = PlatformAPI(fake, remote_mode=remote_mode)
        server = ThreadingHTTPServer(("127.0.0.1", 0), api.handler_class())
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return fake, server, thread

    def _request(self, server, method, path, body=None, token=None):
        con = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-Ivy-Company-Token"] = token
        con.request(method, path, body=json.dumps(body).encode() if body is not None else None,
                    headers=headers)
        response = con.getresponse()
        status = response.status
        payload = json.loads(response.read())
        con.close()
        return status, payload

    def test_http_bridge_authenticated_and_csrf_not_reused(self):
        service, server, thread = self._server()
        try:
            status, body = self._request(server, "GET", "/api/v1/company/status")
            self.assertEqual(status, 403)
            status, body = self._request(server, "GET", "/api/v1/company/status",
                                         token=TOKEN)
            self.assertEqual(status, 200)
            self.assertEqual(body["integration"], "ai_company_os")
            self.assertNotIn("csrf", body)
            status, body = self._request(
                server, "POST", "/api/v1/company/missions",
                body={"goal": "Build demo", "project_slug": "demo"}, token=TOKEN,
            )
            self.assertEqual(status, 201)
            self.assertEqual(body["mission_id"], "mission-123")
            self.assertEqual(service.calls, [("Build demo", "demo", 1)])
            status, body = self._request(
                server, "POST", "/api/v1/company/missions",
                body={"goal": "Build demo", "project_slug": "demo", "approved_build": True},
                token=TOKEN,
            )
            self.assertEqual(status, 400)
            self.assertEqual(len(service.calls), 1)
            status, body = self._request(
                server, "POST", "/api/v1/company/missions",
                body={"goal": "Build demo", "project_slug": "missing"}, token=TOKEN,
            )
            self.assertEqual(status, 404)
            self.assertNotIn("private user path", str(body))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_http_bridge_disabled_or_remote_bound_refuses_mutations(self):
        for disabled, remote_mode in [(True, False), (False, True)]:
            with self.subTest(disabled=disabled, remote_mode=remote_mode):
                fake, server, thread = self._server(with_token=not disabled,
                                                     remote_mode=remote_mode)
                try:
                    status, _ = self._request(
                        server, "POST", "/api/v1/company/missions",
                        body={"goal": "demo", "project_slug": "demo"}, token=TOKEN,
                    )
                    self.assertEqual(status, 403)
                    self.assertEqual(fake.calls, [])
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=5)

    def test_occupied_port_does_not_initialize_service(self):
        with socket.socket() as other:
            other.bind(("127.0.0.1", 0))
            other.listen()
            occupied_port = other.getsockname()[1]
            with patch("src.core.platform_api.PlatformAPI") as create_api:
                with self.assertRaisesRegex(RuntimeError, "already own the port"):
                    serve("127.0.0.1", occupied_port)
                create_api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
