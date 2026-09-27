from __future__ import annotations

import json
import threading
import urllib.request
import urllib.error

from src.core.platform_api import PlatformAPI
from src.core.platform_service import PlatformService
from http.server import ThreadingHTTPServer


def request(port: int, method: str, path: str, payload=None, csrf: str = ""):
    headers = {}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if csrf:
        headers["X-CSRF-Token"] = csrf
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def main() -> int:
    api = PlatformAPI(PlatformService())
    server = ThreadingHTTPServer(("127.0.0.1", 0), api.handler_class())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = int(server.server_address[1])
    try:
        status, data = request(port, "GET", "/api/v1/status")
        if status != 200 or not data.get("capabilities", {}).get("agent_planning"):
            raise RuntimeError("status endpoint did not expose platform capabilities")
        csrf = str(data.get("csrf") or "")
        if not csrf:
            raise RuntimeError("status endpoint did not return CSRF token")

        status, denied = request(port, "POST", "/api/v1/agent/plan", {"goal": "demo"})
        if status != 403:
            raise RuntimeError("mutating API accepted a request without CSRF protection")

        status, plan = request(
            port,
            "POST",
            "/api/v1/agent/plan",
            {"goal": "SNS投稿アプリを改善する"},
            csrf,
        )
        if status != 200 or len(plan.get("steps") or []) < 8:
            raise RuntimeError("agent plan endpoint failed")

        status, projects = request(port, "GET", "/api/v1/projects")
        if status != 200 or not isinstance(projects.get("projects"), list):
            raise RuntimeError("projects endpoint failed")

        print("PLATFORM API ACCEPTANCE PASS: loopback API + CSRF + agent plan + project catalog")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
