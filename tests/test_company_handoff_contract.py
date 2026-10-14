"""Lock down the API contract used by AI COMPANY OS's local Ivy bridge."""
from __future__ import annotations

import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from src.core.platform_api import PlatformAPI


class FakeService:
    def __init__(self):
        self.missions = {}
        self.created = 0

    def status(self):
        return {"ok": True, "service": "ivy-test"}

    def create_mission(self, *, goal, project_slug, max_cycles=8):
        self.created += 1
        mission = {
            "mission_id": "a" * 32,
            "goal": goal,
            "project_slug": project_slug,
            "status": "queued",
            "phase": "planned",
            "max_cycles": max_cycles,
            "requires_approval": False,
        }
        self.missions[mission["mission_id"]] = mission
        return mission

    def mission_detail(self, mission_id):
        return self.missions[mission_id]


class CompanyHandoffAPIContract(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        self.api = PlatformAPI(self.service)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.api.handler_class())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 3)
        self.addCleanup(self.server.shutdown)

    def call(self, method, path, *, body=None, csrf=""):
        con = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=3)
        headers = {}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            con.request(method, path, body=payload, headers=headers)
            resp = con.getresponse()
            return resp.status, json.loads(resp.read().decode("utf-8"))
        finally:
            con.close()

    def test_company_handoff_queues_but_does_not_execute(self):
        status, identity = self.call("GET", "/api/v1/status")
        self.assertEqual(status, 200)
        csrf = identity["csrf"]
        body = {
            "goal": "新しい会社ホームページを作って、公開前に確認",
            "project_slug": "company-site",
            "max_cycles": 4,
        }
        denied, _ = self.call("POST", "/api/v1/missions", body=body)
        self.assertEqual(denied, 403)
        self.assertEqual(self.service.created, 0)
        accepted, mission = self.call("POST", "/api/v1/missions", body=body, csrf=csrf)
        self.assertEqual(accepted, 201)
        self.assertEqual(mission["mission_id"], "a" * 32)
        self.assertEqual(mission["status"], "queued")
        self.assertEqual(mission["max_cycles"], 4)
        self.assertEqual(self.service.created, 1)
        found, current = self.call("GET", "/api/v1/missions/" + mission["mission_id"])
        self.assertEqual(found, 200)
        self.assertEqual(current["phase"], "planned")
        self.assertEqual(self.service.created, 1)


if __name__ == "__main__":
    unittest.main()
