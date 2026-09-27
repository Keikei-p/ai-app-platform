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
                    if path == "/api/v1/agents":
                        self._json(200, {"agents": api.service.specialist_agents()})
                        return
                    if path == "/api/v1/models/routes":
                        self._json(200, api.service.model_routes())
                        return
                    if path == "/api/v1/knowledge":
                        query = parse_qs(parsed.query).get("q", [""])[0]
                        self._json(200, {"knowledge": api.service.verified_knowledge(query)})
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
                    if path == "/api/v1/chat/turn":
                        thread_id = str(data.get("thread_id") or "").strip()
                        message = str(data.get("message") or "").strip()
                        if not thread_id or not message:
                            raise ValueError("thread_id and message are required")
                        row = api.service.chat_turn(thread_id, message)
                        self._json(200, row)
                        return
                    if path == "/api/v1/projects":
                        name = str(data.get("name") or "").strip()
                        if not name:
                            raise ValueError("project name is required")
                        row = api.service.create_project(name, str(data.get("thread_id") or "") or None)
                        self._json(201, row)
                        return
                    if path == "/api/v1/models/routes":
                        capability = str(data.get("capability") or "").strip()
                        provider = str(data.get("provider") or "").strip()
                        model = str(data.get("model") or "").strip()
                        if not capability or not provider:
                            raise ValueError("capability and provider are required")
                        row = api.service.configure_model_route(capability, provider, model)
                        self._json(200, row)
                        return
                    if path == "/api/v1/agent/plan":
                        goal = str(data.get("goal") or "").strip()
                        if not goal:
                            raise ValueError("goal is required")
                        row = api.service.agent_plan(goal, str(data.get("project_slug") or "") or None)
                        self._json(200, row)
                        return
                    if path == "/api/v1/agent/council":
                        goal = str(data.get("goal") or "").strip()
                        context = data.get("context")
                        if not goal:
                            raise ValueError("goal is required")
                        if context is not None and not isinstance(context, dict):
                            raise ValueError("context must be an object")
                        row = api.service.run_specialist_council(
                            goal,
                            project_slug=str(data.get("project_slug") or "") or None,
                            context=context or {},
                        )
                        self._json(200, row)
                        return
                    if path == "/api/v1/research/fetch":
                        url = str(data.get("url") or "").strip()
                        if not url:
                            raise ValueError("url is required")
                        row = api.service.fetch_research_source(url)
                        self._json(200 if row.get("safe_for_reasoning") else 422, row)
                        return
                    if path == "/api/v1/research/intake":
                        topic = str(data.get("topic") or "").strip()
                        statement = str(data.get("statement") or "").strip()
                        sources = data.get("sources")
                        if not topic or not statement or not isinstance(sources, list):
                            raise ValueError("topic, statement and sources are required")
                        row = api.service.research_intake(
                            topic=topic,
                            statement=statement,
                            sources=sources,
                        )
                        self._json(202 if row.get("accepted") else 422, row)
                        return
                    parts = [x for x in path.split("/") if x]
                    if len(parts) == 5 and parts[:3] == ["api", "v1", "projects"] and parts[4] == "build":
                        instruction = str(data.get("instruction") or "").strip()
                        if not instruction:
                            raise ValueError("instruction is required")
                        result = api.service.build_project(
                            parts[3],
                            instruction,
                            approved=data.get("approved") is True,
                            thread_id=str(data.get("thread_id") or "") or None,
                        )
                        self._json(200, api.service.core_result_dict(result))
                        return
                    if len(parts) == 5 and parts[:3] == ["api", "v1", "agents"] and parts[4] == "consult":
                        specialist_name = parts[3]
                        task = str(data.get("task") or "").strip()
                        context = data.get("context")
                        if not task:
                            raise ValueError("task is required")
                        if context is not None and not isinstance(context, dict):
                            raise ValueError("context must be an object")
                        row = api.service.consult_specialist(
                            specialist_name,
                            task,
                            context or {},
                        )
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
