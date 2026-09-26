from __future__ import annotations

import base64
import json
import socket
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .database import log_event
from .mobile_controller import MOBILE_CONTROLLER_HTML
from .remote import RemoteCommand, RemoteCommandGate
from .remote_devices import RemoteDeviceStore
from .remote_pairing import PairingManager, PairingTicket
from .worker_executor import WorkerExecutor

MAX_HTTP_BODY = 80 * 1024


def best_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = item[4][0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "127.0.0.1"


class _RemoteHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, handler_cls, controller):
        super().__init__(server_address, handler_cls)
        self.controller = controller


class RemoteServerController:
    """LAN-only remote server controller.

    Default binding is localhost. LAN mode must be explicitly started by the local user.
    This component intentionally has no UPnP, port-forwarding, tunnel, or public-cloud code.
    """

    def __init__(self, device_store: RemoteDeviceStore | None = None):
        self.devices = device_store or RemoteDeviceStore()
        self.pairing = PairingManager()
        self.worker = WorkerExecutor()
        self._server: _RemoteHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._exec_lock = threading.Lock()
        self._host = "127.0.0.1"
        self._port = 0

    @property
    def running(self) -> bool:
        return bool(self._server and self._thread and self._thread.is_alive())

    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        if not self.running:
            return ""
        host = best_lan_ip() if self._host == "0.0.0.0" else self._host
        return f"http://{host}:{self._port}/"

    def start(self, *, lan: bool = False, port: int = 0) -> str:
        if self.running:
            return self.url
        self._host = "0.0.0.0" if lan else "127.0.0.1"
        self._server = _RemoteHTTPServer((self._host, int(port)), _RemoteHandler, self)
        self._port = int(self._server.server_address[1])
        self.devices.set_enabled(True)
        self._thread = threading.Thread(target=self._server.serve_forever, name="AIAppRemote", daemon=True)
        self._thread.start()
        log_event("remote.server.started", json.dumps({"lan": lan, "port": self._port}), actor="remote-control")
        return self.url

    def stop(self, *, emergency: bool = False) -> None:
        self.pairing.invalidate()
        self.devices.set_enabled(False)
        server = self._server
        self._server = None
        if server:
            server.shutdown()
            server.server_close()
        thread = self._thread
        self._thread = None
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)
        log_event("remote.server.emergency_stop" if emergency else "remote.server.stopped", "stopped", actor="remote-control")

    def create_pairing(self) -> PairingTicket:
        if not self.running:
            raise RuntimeError("remote_server_not_running")
        ticket = self.pairing.create()
        log_event("remote.pairing.created", json.dumps({"expires_at": ticket.expires_at}), actor="remote-control")
        return ticket

    def pair_device(self, code: str, name: str) -> dict:
        if not self.devices.is_enabled() or not self.pairing.consume(code):
            raise PermissionError("invalid_or_expired_pairing_code")
        device, secret = self.devices.pair(name)
        return {"device_id": device.device_id, "name": device.name, "secret_b64": base64.b64encode(secret).decode("ascii")}

    def execute_signed(self, device_id: str, command_raw: dict, signature: str) -> dict:
        if not self.devices.is_enabled():
            raise PermissionError("remote_disabled")
        secret = self.devices.secret_for(device_id)
        if not secret:
            raise PermissionError("unknown_or_revoked_device")
        try:
            command = RemoteCommand(
                command_id=str(command_raw["command_id"]),
                issued_at=int(command_raw["issued_at"]),
                expires_at=int(command_raw["expires_at"]),
                action=str(command_raw["action"]),
                project_slug=command_raw.get("project_slug"),
                payload=command_raw.get("payload") if isinstance(command_raw.get("payload"), dict) else {},
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid_command_shape") from exc
        gate = RemoteCommandGate(secret)
        accepted = gate.accept(command, signature)
        if not accepted.accepted:
            raise PermissionError(accepted.reason)
        with self._exec_lock:
            result = self.worker.execute(command.action, command.project_slug, command.payload)
        log_event("remote.command.executed", json.dumps({"device_id": device_id, "action": command.action, "ok": result.ok}), command.project_slug, "remote-worker")
        return {"ok": result.ok, "action": result.action, "data": result.data}


class _RemoteHandler(BaseHTTPRequestHandler):
    server_version = "AIAppRemote/0.4.8"
    protocol_version = "HTTP/1.1"

    @property
    def controller(self) -> RemoteServerController:
        return self.server.controller  # type: ignore[attr-defined]

    def log_message(self, _format, *_args):
        return

    def _headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline' 'self'; style-src 'unsafe-inline' 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()

    def _send_bytes(self, status: int, data: bytes, content_type: str) -> None:
        self._headers(status, content_type, len(data))
        self.wfile.write(data)

    def _json(self, status: int, payload: dict) -> None:
        self._send_bytes(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid_content_length")
        if length <= 0 or length > MAX_HTTP_BODY:
            raise ValueError("invalid_body_size")
        raw = self.rfile.read(length)
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_json") from exc
        if not isinstance(obj, dict):
            raise ValueError("json_object_required")
        return obj

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_bytes(HTTPStatus.OK, MOBILE_CONTROLLER_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/health":
            self._json(HTTPStatus.OK, {"ok": True, "mode": "lan-beta"})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            body = self._read_json()
            if parsed.path == "/api/pair":
                result = self.controller.pair_device(str(body.get("code") or ""), str(body.get("name") or "スマホ"))
                self._json(HTTPStatus.OK, result)
                return
            if parsed.path == "/api/command":
                device_id = str(self.headers.get("X-Device-ID") or "")
                command = body.get("command")
                if not isinstance(command, dict):
                    raise ValueError("command_required")
                result = self.controller.execute_signed(device_id, command, str(body.get("signature") or ""))
                self._json(HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST, result)
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except PermissionError as exc:
            self._json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
        except (ValueError, RuntimeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal_error"})
