from __future__ import annotations

import urllib.request
import importlib.util
import json
import tempfile
import threading
import time
from pathlib import Path

from src.core.app_spec import AppSpec
from src.core.generator import StarterGenerator
from src.core.social_generator import SocialAutomationGenerator


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
            raw = response.read()
            return response.status, json.loads(raw or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw or b"{}")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load generated module")
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "project.json").write_text(
            '{"name":"SNS Acceptance","slug":"sns-acceptance"}',
            encoding="utf-8",
        )
        spec = AppSpec(
            "SNS Acceptance",
            "sns-acceptance",
            "ThreadsとXへ予約自動投稿",
            "social_automation",
            ["scheduler", "social_publish"],
            ["web"],
        )
        spec.save(root)
        StarterGenerator().generate_from_spec(root, spec)
        SocialAutomationGenerator().generate(root, spec)

        import sys
        sys.path.insert(0, str(root))
        try:
            server_mod = load_module(root / "server.py", "generated_social_server_acceptance")
            server = server_mod.ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_mod.WORKER.start()
            thread.start()
            port = int(server.server_address[1])
            try:
                status, bootstrap = request(port, "GET", "/api/social/bootstrap")
                if status != 200 or not bootstrap.get("credentials", {}).get("dry_run"):
                    raise RuntimeError("SNS bootstrap did not start in dry-run mode")
                csrf = str(bootstrap["csrf"])

                status, created = request(
                    port,
                    "POST",
                    "/api/social/posts",
                    {
                        "platform": "threads",
                        "text": "acceptance post",
                        "scheduled_at": int(time.time()) - 1,
                    },
                    csrf,
                )
                if status != 201:
                    raise RuntimeError("could not enqueue SNS post: " + repr(created))
                post = created["post"]
                if post["status"] != "pending_approval":
                    raise RuntimeError("default mode did not require approval")

                status, approved = request(
                    port,
                    "POST",
                    f"/api/social/posts/{post['id']}/approve",
                    {},
                    csrf,
                )
                if status != 200 or not approved.get("ok"):
                    raise RuntimeError("could not approve SNS post")

                deadline = time.time() + 8
                posted = None
                while time.time() < deadline:
                    status, rows = request(port, "GET", "/api/social/posts")
                    if status != 200:
                        raise RuntimeError("could not read SNS queue")
                    posted = next((x for x in rows["posts"] if x["id"] == post["id"]), None)
                    if posted and posted["status"] == "posted":
                        break
                    time.sleep(0.25)
                if not posted or posted["status"] != "posted":
                    raise RuntimeError("approved SNS post was not processed by worker")
                if not str(posted["remote_id"]).startswith("dryrun-"):
                    raise RuntimeError("acceptance unexpectedly sent an external request")

                status, mode = request(
                    port,
                    "POST",
                    "/api/social/settings",
                    {"auto_mode": True},
                    csrf,
                )
                if status != 200 or not mode.get("auto_mode"):
                    raise RuntimeError("could not enable SNS auto mode")

                status, auto_created = request(
                    port,
                    "POST",
                    "/api/social/posts",
                    {
                        "platform": "x",
                        "text": "automatic acceptance post",
                        "scheduled_at": int(time.time()) - 1,
                        "idempotency_key": "acceptance-auto",
                    },
                    csrf,
                )
                if status != 201 or auto_created["post"]["status"] != "queued":
                    raise RuntimeError("auto mode did not queue post directly")

                print("SNS AUTOMATION ACCEPTANCE PASS: queue -> approve/auto -> dry-run worker -> posted")
            finally:
                server.shutdown()
                server.server_close()
                server_mod.WORKER.stop()
        finally:
            if str(root) in sys.path:
                sys.path.remove(str(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
