from __future__ import annotations

import base64
import hmac
import hashlib
import json
import re
import subprocess
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

from src.core.mobile_controller import MOBILE_CONTROLLER_HTML
from src.core.remote import RemoteCommand, sign_command
from src.core.remote_devices import RemoteDeviceStore
from src.core.remote_server import RemoteServerController


def _post(url: str, payload: dict, headers: dict | None = None) -> tuple[int, dict]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _check_mobile_hmac() -> None:
    # Verify the exact JavaScript HMAC code embedded in the mobile page against Python.
    if not __import__("shutil").which("node"):
        print("REMOTE_ACCEPTANCE: Node missing; mobile JS HMAC check skipped")
        return
    script = re.search(r"<script>(.*)</script>", MOBILE_CONTROLLER_HTML, re.S)
    if not script:
        raise RuntimeError("mobile script missing")
    js = script.group(1).rsplit("show();", 1)[0]
    secret = b"r" * 32
    secret_b64 = base64.b64encode(secret).decode("ascii")
    canonical = '{"action":"status","command_id":"abc","expires_at":200,"issued_at":100,"payload":{},"project_slug":null}'
    expected = hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    code = js + f"\nconsole.log(hmacHexSync('{secret_b64}', {json.dumps(canonical)}));\n"
    proc = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=8)
    if proc.returncode != 0:
        raise RuntimeError("mobile JS failed: " + proc.stderr[-500:])
    actual = proc.stdout.strip().splitlines()[-1]
    if actual != expected:
        raise RuntimeError("mobile HMAC mismatch")


def main() -> int:
    _check_mobile_hmac()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        store = RemoteDeviceStore(root / "devices.json", root / "settings.json")
        controller = RemoteServerController(store)
        try:
            controller.start(lan=False, port=0)
            base = f"http://127.0.0.1:{controller.port}"
            ticket = controller.create_pairing()
            status, paired = _post(base + "/api/pair", {"code": ticket.code, "name": "Acceptance Phone"})
            if status != 200:
                raise RuntimeError(f"pair failed: {paired}")
            secret = base64.b64decode(paired["secret_b64"])
            device_id = paired["device_id"]

            now = int(time.time())
            cmd = RemoteCommand("accept-" + uuid.uuid4().hex, now, now + 120, "status", None, {})
            sig = sign_command(cmd, secret)
            status, result = _post(base + "/api/command", {"command": cmd.__dict__, "signature": sig}, {"X-Device-ID": device_id})
            if status != 200 or not result.get("ok"):
                raise RuntimeError(f"signed status failed: {result}")

            status2, replay = _post(base + "/api/command", {"command": cmd.__dict__, "signature": sig}, {"X-Device-ID": device_id})
            if status2 != 403 or replay.get("error") != "replay_or_duplicate_command":
                raise RuntimeError(f"replay was not rejected: {status2} {replay}")

            # Full remote task flow: create project -> generate -> test -> Code Vault.
            project_name = "Remote Acceptance " + uuid.uuid4().hex[:8]
            def send(action, project_slug=None, payload=None):
                ts = int(time.time())
                c = RemoteCommand("flow-" + uuid.uuid4().hex, ts, ts + 120, action, project_slug, payload or {})
                sg = sign_command(c, secret)
                return _post(base + "/api/command", {"command": c.__dict__, "signature": sg}, {"X-Device-ID": device_id})

            created_status, created = send("project_create", None, {"name": project_name})
            if created_status != 200 or not created.get("ok"):
                raise RuntimeError(f"project create failed: {created}")
            slug = created["data"]["slug"]
            try:
                pipe_status, pipeline = send("run_pipeline", slug, {"instruction": "シンプルなToDoアプリを作って"})
                if pipe_status != 200 or not pipeline.get("ok"):
                    raise RuntimeError(f"remote pipeline failed: {pipeline}")
                test_status, tests = send("run_tests", slug, {})
                if test_status != 200 or not tests.get("ok"):
                    raise RuntimeError(f"remote tests failed: {tests}")
                vault_status, vault = send("vault_save", slug, {})
                if vault_status != 200 or not vault.get("ok"):
                    raise RuntimeError(f"remote vault failed: {vault}")
            finally:
                from src.core.config import WORKSPACE_DIR
                from src.core.database import delete_project_record
                import shutil
                shutil.rmtree(WORKSPACE_DIR / slug, ignore_errors=True)
                delete_project_record(slug)

            controller.devices.revoke(device_id)
            cmd2 = RemoteCommand("rev-" + uuid.uuid4().hex, now, now + 120, "status", None, {})
            sig2 = sign_command(cmd2, secret)
            status3, revoked = _post(base + "/api/command", {"command": cmd2.__dict__, "signature": sig2}, {"X-Device-ID": device_id})
            if status3 != 403 or revoked.get("error") != "unknown_or_revoked_device":
                raise RuntimeError(f"revoked device not rejected: {status3} {revoked}")
        finally:
            controller.stop(emergency=True)
        if store.is_enabled():
            raise RuntimeError("emergency stop did not disable remote")
    print("REMOTE_ACCEPTANCE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
