from __future__ import annotations

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from typing import Any
import argparse
import json
import os
import secrets

from .platform_service import PlatformService
from .config import ROOT_DIR


MAX_BODY = 1024 * 1024


class PlatformAPI:
    """Loopback-only JSON API for future React/Tauri and CLI clients."""

    def __init__(self, service: PlatformService | None = None):
        self.service = service or PlatformService()
        self.csrf = secrets.token_urlsafe(24)

    def handler_class(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AIAppPlatform/0.9"

            def log_message(self, fmt, *args):
                pass

            def _json(self, status: int, data: Any):
                raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(raw)

            def _asset(self, relative: str, content_type: str):
                path = (ROOT_DIR / "webui" / relative).resolve()
                root = (ROOT_DIR / "webui").resolve()
                if root not in path.parents and path != root:
                    self._json(404, {"error": "not_found"})
                    return
                if not path.is_file():
                    self._json(404, {"error": "not_found"})
                    return
                raw = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(raw)

            def _body(self) -> dict[str, Any]:
                size = int(self.headers.get("Content-Length") or 0)
                if size < 0 or size > MAX_BODY:
                    raise ValueError("request_too_large")
                raw = self.rfile.read(size) if size else b"{}"
                data = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(data, dict):
                    raise ValueError("JSON object required")
                return data

            def _mutating_allowed(self) -> bool:
                token = self.headers.get("X-CSRF-Token", "")
                if not secrets.compare_digest(token, api.csrf):
                    return False
                configured = os.environ.get("AI_APP_LOCAL_API_TOKEN", "").strip()
                if not configured:
                    return True
                supplied = self.headers.get("Authorization", "")
                return secrets.compare_digest(supplied, "Bearer " + configured)

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"
                try:
                    if path in {"/", "/ui"}:
                        self._asset("index.html", "text/html; charset=utf-8")
                        return
                    if path == "/ui/styles.css":
                        self._asset("styles.css", "text/css; charset=utf-8")
                        return
                    if path == "/ui/app.js":
                        self._asset("app.js", "application/javascript; charset=utf-8")
                        return
                    if path == "/api/v1/status":
                        self._json(200, {**api.service.status(), "csrf": api.csrf})
                        return
                    if path == "/api/v1/projects":
                        self._json(200, {"projects": api.service.list_project_cards()})
                        return
                    if path == "/api/v1/conversations":
                        query = parse_qs(parsed.query).get("q", [""])[0]
                        self._json(200, {"conversations": api.service.list_conversations(query)})
                        return

                    parts = [x for x in path.split("/") if x]
                    if len(parts) == 4 and parts[:3] == ["api", "v1", "projects"]:
                        self._json(200, api.service.project_detail(parts[3]))
                        return
                    if len(parts) == 5 and parts[:3] == ["api", "v1", "projects"] and parts[4] == "deliveries":
                        self._json(200, {"deliveries": api.service.delivery_options(parts[3])})
                        return
                    if len(parts) == 5 and parts[:3] == ["api", "v1", "conversations"] and parts[4] == "messages":
                        self._json(200, {"messages": api.service.conversation_messages(parts[3])})
                        return
                    self._json(404, {"error": "not_found"})
                except FileNotFoundError:
                    self._json(404, {"error": "not_found"})
                except Exception as exc:
                    self._json(400, {"error": str(exc)})

            def do_POST(self):
                path = urlparse(self.path).path.rstrip("/")
                if not self._mutating_allowed():
                    self._json(403, {"error": "mutation_not_authorized"})
                    return
                try:
                    data = self._body()
                    if path == "/api/v1/conversations":
                        row = api.service.create_conversation(str(data.get("title") or "新しいチャット"))
                        self._json(201, row)
                        return
                    if path == "/api/v1/projects":
                        name = str(data.get("name") or "").strip()
                        if not name:
                            raise ValueError("project name is required")
                        row = api.service.create_project(name, str(data.get("thread_id") or "") or None)
                        self._json(201, row)
                        return
                    if path == "/api/v1/agent/plan":
                        goal = str(data.get("goal") or "").strip()
                        if not goal:
                            raise ValueError("goal is required")
                        row = api.service.agent_plan(goal, str(data.get("project_slug") or "") or None)
                        self._json(200, row)
                        return
                    self._json(404, {"error": "not_found"})
                except Exception as exc:
                    self._json(400, {"error": str(exc)})

        return Handler


def serve(host: str = "127.0.0.1", port: int = 8766) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("Platform API is loopback-only")
    api = PlatformAPI()
    server = ThreadingHTTPServer((host, port), api.handler_class())
    print(f"AI App Platform local API: http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
