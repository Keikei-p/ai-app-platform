"""Real Aivy API smoke & restart integration; no fake PlatformService.

The server is a child process using an isolated state directory. This test
makes no paid API calls and never starts an approved build or publication.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
OPENER = request.build_opener(request.ProxyHandler({}))


def unused_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class RealPlatformBridgeRestartTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aivy-bridge-real-")
        self.addCleanup(self.temp.cleanup)
        self.state_dir = Path(self.temp.name) / "state"
        self.log_path = Path(self.temp.name) / "api.log"
        self.port = unused_port()
        self.process = None
        self.url = f"http://127.0.0.1:{self.port}"
        self.addCleanup(self.stop_server)

    def call(self, path, *, body=None, csrf=None, timeout=8):
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            if csrf:
                headers["X-CSRF-Token"] = csrf
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.url + path,
            data=data,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
        try:
            with OPENER.open(req, timeout=timeout) as response:
                return response.status, json.loads(response.read())
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def start_server(self):
        self.assertIsNone(self.process)
        env = os.environ.copy()
        env["AI_APP_PLATFORM_STATE_DIR"] = str(self.state_dir)
        env.pop("AI_APP_LOCAL_API_TOKEN", None)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with self.log_path.open("ab") as logfile:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "src.core.platform_api",
                 "--host", "127.0.0.1", "--port", str(self.port)],
                cwd=str(ROOT), env=env,
                stdout=logfile, stderr=subprocess.STDOUT,
                creationflags=flags,
            )
        deadline = time.monotonic() + 55
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.fail("Aivy process exited early; log: " +
                          self.log_path.read_text(encoding="utf-8", errors="replace")[-2500:])
            try:
                status, data = self.call("/api/v1/status", timeout=2)
                if status == 200 and data.get("service") == "ai-app-platform":
                    self.assertTrue(data.get("csrf"))
                    return data
            except (OSError, ValueError, error.URLError):
                time.sleep(0.3)
        self.fail("Aivy did not start; log: " +
                  self.log_path.read_text(encoding="utf-8", errors="replace")[-2500:])

    def stop_server(self):
        process = self.process
        self.process = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=8)

    def test_real_app_project_mission_api_and_restart(self):
        initial = self.start_server()
        csrf = initial["csrf"]
        no_csrf, _ = self.call("/api/v1/projects", body={"name": "採用ホームページ"})
        self.assertEqual(no_csrf, 403, "Real Ivy must block unauthenticated mutation")

        created, project = self.call(
            "/api/v1/projects", body={"name": "採用ホームページ"}, csrf=csrf,
            timeout=30,
        )
        self.assertEqual(created, 201, project)
        slug = project["slug"]
        self.assertTrue((self.state_dir / "workspace" / slug / "project.json").is_file())

        accepted, mission = self.call(
            "/api/v1/missions",
            body={"project_slug": slug, "goal": "スマホ対応の採用サイトを制作", "max_cycles": 4},
            csrf=csrf, timeout=30,
        )
        self.assertEqual(accepted, 201, mission)
        mid = mission["mission_id"]
        self.assertEqual(len(mid), 32)
        self.assertEqual(mission["status"], "queued")

        for _ in range(20):
            read, state = self.call("/api/v1/missions/" + mid)
            self.assertEqual(read, 200)
            self.assertEqual(state["mission_id"], mid)
            self.assertEqual(state["status"], "queued")

        refused, _ = self.call(
            "/api/v1/missions/" + mid + "/run",
            body={"approved_build": True}, timeout=10,
        )
        self.assertEqual(refused, 403, "Aivy must block unapproved build request")
        self.stop_server()

        restarted = self.start_server()
        self.assertNotEqual(restarted["csrf"], csrf, "CSRF secret must rotate on restart")
        read, recovered = self.call("/api/v1/missions/" + mid)
        self.assertEqual(read, 200, recovered)
        self.assertEqual(recovered["mission_id"], mid)
        self.assertEqual(recovered["project_slug"], slug)
        self.assertEqual(recovered["status"], "queued")
        read, details = self.call("/api/v1/projects/" + slug)
        self.assertEqual(read, 200, details)
        self.assertTrue((self.state_dir / "workspace" / slug / "project.json").is_file())
        print("REAL-IVY-E2E-PASS: actual process, project, mission, 20 API polls, auth and restart")


if __name__ == "__main__":
    unittest.main()
