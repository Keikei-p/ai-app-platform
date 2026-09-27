from __future__ import annotations

from pathlib import Path
import json

from .app_spec import AppSpec
from .database import log_event


class SocialAutomationGenerator:
    """Generate a local-first SNS scheduling/control application."""

    def generate(self, project_dir: Path, spec: AppSpec) -> list[Path]:
        if spec.app_type != "social_automation" and "social_publish" not in spec.features:
            return []

        media_dir = project_dir / "media"
        media_dir.mkdir(exist_ok=True)

        files = {
            "social_runtime.py": self._runtime(),
            "server.py": self._server(),
            "index.html": self._index(spec),
            "app.js": self._script(),
            "social.css": self._styles(),
            "SOCIAL_AUTOMATION.md": self._readme(),
            "social_provider_contract.json": json.dumps(
                {
                    "default_mode": "dry-run",
                    "providers": {
                        "x": {"supports": ["text"], "env": ["X_ACCESS_TOKEN"]},
                        "threads": {"supports": ["text"], "env": ["THREADS_USER_ID", "THREADS_ACCESS_TOKEN"]},
                        "instagram": {
                            "supports": ["image_url"],
                            "env": ["INSTAGRAM_USER_ID", "INSTAGRAM_ACCESS_TOKEN", "META_GRAPH_API_BASE"],
                        },
                        "youtube": {
                            "supports": ["video_file"],
                            "env": ["YOUTUBE_ACCESS_TOKEN"],
                            "video_root": "media/",
                        },
                    },
                    "safety": {
                        "credentials_persisted": False,
                        "auto_mode_default": False,
                        "dry_run_default": True,
                        "max_attempts": 5,
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
        }

        out: list[Path] = []
        for name, body in files.items():
            path = project_dir / name
            path.write_text(body, encoding="utf-8")
            out.append(path)

        log_event("generator.social", "Generated SNS automation runtime", spec.slug)
        return out

    @staticmethod
    def _runtime() -> str:
        return r'''from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import hashlib
import json
import mimetypes
from contextlib import contextmanager
import os
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "social_queue.db"
MEDIA_ROOT = ROOT / "media"
SUPPORTED_PLATFORMS = {"x", "threads", "instagram", "youtube"}
MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class PublishResult:
    remote_id: str
    detail: str


def utc_ts() -> int:
    return int(time.time())


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def is_dry_run() -> bool:
    return _env("SOCIAL_DRY_RUN") != "0"


def _json_request(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read()
    data = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(data, dict):
        raise RuntimeError("provider returned invalid JSON")
    return data


def _form_request(url: str, payload: dict[str, Any]) -> dict:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read()
    data = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(data, dict):
        raise RuntimeError("provider returned invalid JSON")
    return data


class Provider:
    def publish(self, post: dict[str, Any]) -> PublishResult:
        raise NotImplementedError


class DryRunProvider(Provider):
    def publish(self, post: dict[str, Any]) -> PublishResult:
        digest = hashlib.sha256(
            (str(post.get("idempotency_key")) + str(post.get("platform"))).encode("utf-8")
        ).hexdigest()[:18]
        return PublishResult("dryrun-" + digest, "dry-run only; no external request sent")


class XProvider(Provider):
    def publish(self, post: dict[str, Any]) -> PublishResult:
        token = _env("X_ACCESS_TOKEN")
        if not token:
            raise RuntimeError("X_ACCESS_TOKEN is not configured")
        text = str(post.get("text") or "").strip()
        if not text:
            raise RuntimeError("X text is empty")
        data = _json_request(
            "https://api.x.com/2/tweets",
            {"text": text},
            {"Authorization": "Bearer " + token},
        )
        remote_id = str((data.get("data") or {}).get("id") or "")
        if not remote_id:
            raise RuntimeError("X API did not return a post id")
        return PublishResult(remote_id, "published to X")


class ThreadsProvider(Provider):
    def publish(self, post: dict[str, Any]) -> PublishResult:
        user_id = _env("THREADS_USER_ID")
        token = _env("THREADS_ACCESS_TOKEN")
        if not user_id or not token:
            raise RuntimeError("Threads credentials are not configured")
        base = _env("THREADS_GRAPH_BASE") or "https://graph.threads.net/v1.0"
        create = _form_request(
            base.rstrip("/") + "/" + urllib.parse.quote(user_id) + "/threads",
            {
                "media_type": "TEXT",
                "text": str(post.get("text") or ""),
                "access_token": token,
            },
        )
        creation_id = str(create.get("id") or "")
        if not creation_id:
            raise RuntimeError("Threads API did not return creation id")
        published = _form_request(
            base.rstrip("/") + "/" + urllib.parse.quote(user_id) + "/threads_publish",
            {"creation_id": creation_id, "access_token": token},
        )
        remote_id = str(published.get("id") or "")
        if not remote_id:
            raise RuntimeError("Threads API did not return published id")
        return PublishResult(remote_id, "published to Threads")


class InstagramProvider(Provider):
    def publish(self, post: dict[str, Any]) -> PublishResult:
        user_id = _env("INSTAGRAM_USER_ID")
        token = _env("INSTAGRAM_ACCESS_TOKEN")
        base = _env("META_GRAPH_API_BASE")
        media_url = str(post.get("media_url") or "").strip()
        if not user_id or not token or not base:
            raise RuntimeError("Instagram credentials/API base are not configured")
        if not media_url.startswith(("https://", "http://")):
            raise RuntimeError("Instagram requires a public media_url")
        create = _form_request(
            base.rstrip("/") + "/" + urllib.parse.quote(user_id) + "/media",
            {
                "image_url": media_url,
                "caption": str(post.get("text") or ""),
                "access_token": token,
            },
        )
        creation_id = str(create.get("id") or "")
        if not creation_id:
            raise RuntimeError("Instagram API did not return creation id")
        published = _form_request(
            base.rstrip("/") + "/" + urllib.parse.quote(user_id) + "/media_publish",
            {"creation_id": creation_id, "access_token": token},
        )
        remote_id = str(published.get("id") or "")
        if not remote_id:
            raise RuntimeError("Instagram API did not return published id")
        return PublishResult(remote_id, "published to Instagram")


class YouTubeProvider(Provider):
    def publish(self, post: dict[str, Any]) -> PublishResult:
        token = _env("YOUTUBE_ACCESS_TOKEN")
        if not token:
            raise RuntimeError("YOUTUBE_ACCESS_TOKEN is not configured")
        video_path = _safe_media_path(str(post.get("video_path") or ""))
        metadata = post.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        title = str(metadata.get("title") or post.get("text") or "Untitled")[:100]
        description = str(metadata.get("description") or post.get("text") or "")
        privacy = str(metadata.get("privacyStatus") or "private")
        if privacy not in {"private", "unlisted", "public"}:
            privacy = "private"

        boundary = "aiapp-" + uuid.uuid4().hex
        meta = json.dumps(
            {
                "snippet": {"title": title, "description": description},
                "status": {"privacyStatus": privacy},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        video = video_path.read_bytes()
        mime = mimetypes.guess_type(video_path.name)[0] or "application/octet-stream"
        body = (
            ("--" + boundary + "\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n").encode()
            + meta
            + ("\r\n--" + boundary + "\r\nContent-Type: " + mime + "\r\n\r\n").encode()
            + video
            + ("\r\n--" + boundary + "--\r\n").encode()
        )
        url = "https://www.googleapis.com/upload/youtube/v3/videos?part=snippet,status&uploadType=multipart"
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "multipart/related; boundary=" + boundary,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8") or "{}")
        remote_id = str(data.get("id") or "")
        if not remote_id:
            raise RuntimeError("YouTube API did not return video id")
        return PublishResult(remote_id, "uploaded to YouTube")


def _safe_media_path(value: str) -> Path:
    if not value:
        raise RuntimeError("video_path is required")
    raw = Path(value)
    if raw.is_absolute():
        target = raw
    elif raw.parts and raw.parts[0].lower() == "media":
        target = ROOT.joinpath(*raw.parts)
    else:
        target = MEDIA_ROOT / raw
    root = MEDIA_ROOT.resolve()
    resolved = target.resolve()
    if resolved != root and root not in resolved.parents:
        raise RuntimeError("video_path must stay inside media/")
    if not resolved.is_file():
        raise RuntimeError("video file was not found")
    return resolved


def provider_for(platform: str) -> Provider:
    if is_dry_run():
        return DryRunProvider()
    mapping: dict[str, type[Provider]] = {
        "x": XProvider,
        "threads": ThreadsProvider,
        "instagram": InstagramProvider,
        "youtube": YouTubeProvider,
    }
    cls = mapping.get(platform)
    if cls is None:
        raise RuntimeError("unsupported platform")
    return cls()


def credential_status() -> dict[str, Any]:
    return {
        "dry_run": is_dry_run(),
        "x": bool(_env("X_ACCESS_TOKEN")),
        "threads": bool(_env("THREADS_USER_ID") and _env("THREADS_ACCESS_TOKEN")),
        "instagram": bool(
            _env("INSTAGRAM_USER_ID")
            and _env("INSTAGRAM_ACCESS_TOKEN")
            and _env("META_GRAPH_API_BASE")
        ),
        "youtube": bool(_env("YOUTUBE_ACCESS_TOKEN")),
    }


class SocialStore:
    def __init__(self, db_path: Path | None = None):
        self.db_path = Path(db_path or DEFAULT_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._ensure()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure(self) -> None:
        with self._connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS social_settings(
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS social_posts(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              platform TEXT NOT NULL,
              text TEXT NOT NULL DEFAULT '',
              media_url TEXT NOT NULL DEFAULT '',
              video_path TEXT NOT NULL DEFAULT '',
              metadata_json TEXT NOT NULL DEFAULT '{}',
              scheduled_at INTEGER NOT NULL,
              status TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              next_attempt_at INTEGER NOT NULL DEFAULT 0,
              last_error TEXT NOT NULL DEFAULT '',
              remote_id TEXT NOT NULL DEFAULT '',
              idempotency_key TEXT NOT NULL UNIQUE,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            );
            """)
            conn.execute(
                "INSERT OR IGNORE INTO social_settings(key,value) VALUES('auto_mode','0')"
            )

    def auto_mode(self) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT value FROM social_settings WHERE key='auto_mode'"
            ).fetchone()
        return bool(row and row["value"] == "1")

    def set_auto_mode(self, enabled: bool) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO social_settings(key,value) VALUES('auto_mode',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                ("1" if enabled else "0",),
            )

    def enqueue(
        self,
        platform: str,
        text: str = "",
        scheduled_at: int | None = None,
        media_url: str = "",
        video_path: str = "",
        metadata: dict[str, Any] | None = None,
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        platform = platform.strip().lower()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError("unsupported platform")
        text = str(text)[:10000]
        media_url = str(media_url)[:4000]
        video_path = str(video_path)[:1000]
        metadata = metadata if isinstance(metadata, dict) else {}
        due = int(scheduled_at or utc_ts())
        if due < 0:
            raise ValueError("scheduled_at must be positive")
        if platform == "instagram" and not media_url:
            raise ValueError("instagram requires media_url")
        if platform == "youtube" and not video_path:
            raise ValueError("youtube requires video_path")
        key = idempotency_key.strip()[:200]
        if not key:
            key = hashlib.sha256(
                json.dumps(
                    [platform, text, media_url, video_path, due, metadata],
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
        now = utc_ts()
        status = "queued" if self.auto_mode() else "pending_approval"
        with self._lock, self._connection() as conn:
            existing = conn.execute(
                "SELECT * FROM social_posts WHERE idempotency_key=?", (key,)
            ).fetchone()
            if existing:
                return self._row(existing)
            cur = conn.execute(
                "INSERT INTO social_posts("
                "platform,text,media_url,video_path,metadata_json,scheduled_at,status,"
                "attempts,next_attempt_at,last_error,remote_id,idempotency_key,created_at,updated_at"
                ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    platform,
                    text,
                    media_url,
                    video_path,
                    json.dumps(metadata, ensure_ascii=False),
                    due,
                    status,
                    0,
                    due,
                    "",
                    "",
                    key,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM social_posts WHERE id=?", (cur.lastrowid,)).fetchone()
        return self._row(row)

    def list_posts(self, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM social_posts ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row(row) for row in rows]

    def counts(self) -> dict[str, int]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT status,COUNT(*) AS n FROM social_posts GROUP BY status"
            ).fetchall()
        result = {str(row["status"]): int(row["n"]) for row in rows}
        for key in ("pending_approval", "queued", "posting", "posted", "retry", "failed", "cancelled"):
            result.setdefault(key, 0)
        return result

    def approve(self, post_id: int) -> bool:
        now = utc_ts()
        with self._connection() as conn:
            cur = conn.execute(
                "UPDATE social_posts SET status='queued',next_attempt_at=scheduled_at,updated_at=? "
                "WHERE id=? AND status='pending_approval'",
                (now, int(post_id)),
            )
        return bool(cur.rowcount)

    def cancel(self, post_id: int) -> bool:
        now = utc_ts()
        with self._connection() as conn:
            cur = conn.execute(
                "UPDATE social_posts SET status='cancelled',updated_at=? "
                "WHERE id=? AND status IN ('pending_approval','queued','retry')",
                (now, int(post_id)),
            )
        return bool(cur.rowcount)

    def retry(self, post_id: int) -> bool:
        now = utc_ts()
        with self._connection() as conn:
            cur = conn.execute(
                "UPDATE social_posts SET status='queued',next_attempt_at=?,last_error='',updated_at=? "
                "WHERE id=? AND status='failed'",
                (now, now, int(post_id)),
            )
        return bool(cur.rowcount)

    def claim_due(self) -> dict[str, Any] | None:
        now = utc_ts()
        with self._lock, self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM social_posts "
                "WHERE status IN ('queued','retry') AND scheduled_at<=? AND next_attempt_at<=? "
                "ORDER BY scheduled_at,id LIMIT 1",
                (now, now),
            ).fetchone()
            if not row:
                return None
            cur = conn.execute(
                "UPDATE social_posts SET status='posting',updated_at=? "
                "WHERE id=? AND status IN ('queued','retry')",
                (now, row["id"]),
            )
            if not cur.rowcount:
                return None
            claimed = conn.execute("SELECT * FROM social_posts WHERE id=?", (row["id"],)).fetchone()
        return self._row(claimed)

    def mark_posted(self, post_id: int, result: PublishResult) -> None:
        now = utc_ts()
        with self._connection() as conn:
            conn.execute(
                "UPDATE social_posts SET status='posted',remote_id=?,last_error='',updated_at=? WHERE id=?",
                (result.remote_id[:500], now, int(post_id)),
            )

    def mark_failed(self, post_id: int, error: str) -> None:
        now = utc_ts()
        with self._connection() as conn:
            row = conn.execute(
                "SELECT attempts FROM social_posts WHERE id=?", (int(post_id),)
            ).fetchone()
            if not row:
                return
            attempts = int(row["attempts"]) + 1
            if attempts >= MAX_ATTEMPTS:
                status = "failed"
                next_attempt = now
            else:
                status = "retry"
                next_attempt = now + min(3600, 30 * (2 ** (attempts - 1)))
            conn.execute(
                "UPDATE social_posts SET status=?,attempts=?,next_attempt_at=?,last_error=?,updated_at=? "
                "WHERE id=?",
                (status, attempts, next_attempt, str(error)[:2000], now, int(post_id)),
            )

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        try:
            data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        except Exception:
            data["metadata"] = {}
            data.pop("metadata_json", None)
        return data


def run_once(store: SocialStore) -> dict[str, Any] | None:
    post = store.claim_due()
    if post is None:
        return None
    try:
        result = provider_for(str(post["platform"])).publish(post)
    except Exception as exc:
        store.mark_failed(int(post["id"]), str(exc))
        return {"ok": False, "id": post["id"], "error": str(exc)}
    store.mark_posted(int(post["id"]), result)
    return {"ok": True, "id": post["id"], **asdict(result)}


class SocialWorker:
    def __init__(self, store: SocialStore, interval_seconds: float = 5.0):
        self.store = store
        self.interval_seconds = max(1.0, float(interval_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="SocialWorker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            while not self._stop.is_set():
                result = run_once(self.store)
                if result is None:
                    break
            self._stop.wait(self.interval_seconds)
'''

    @staticmethod
    def _server() -> str:
        return r'''from __future__ import annotations
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import argparse
import json
import os
import secrets

from social_runtime import SocialStore, SocialWorker, credential_status

ROOT = Path(__file__).resolve().parent
MAX_BODY = 2 * 1024 * 1024
STORE = SocialStore()
WORKER = SocialWorker(STORE)
CSRF = secrets.token_urlsafe(24)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        pass

    def _json(self, status: int, data: dict):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict:
        size = int(self.headers.get("Content-Length") or 0)
        if size > MAX_BODY:
            raise ValueError("request_too_large")
        data = json.loads(self.rfile.read(size) or b"{}")
        if not isinstance(data, dict):
            raise ValueError("JSON object required")
        return data

    def _authorized(self) -> bool:
        configured = os.environ.get("SOCIAL_ADMIN_TOKEN", "").strip()
        if not configured:
            return True
        supplied = self.headers.get("Authorization", "")
        return secrets.compare_digest(supplied, "Bearer " + configured)

    def _csrf_ok(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), CSRF)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/social/bootstrap":
            self._json(
                200,
                {
                    "csrf": CSRF,
                    "auto_mode": STORE.auto_mode(),
                    "credentials": credential_status(),
                    "counts": STORE.counts(),
                },
            )
            return
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        if path == "/api/social/posts":
            self._json(200, {"posts": STORE.list_posts(), "counts": STORE.counts()})
            return
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        if not self._csrf_ok():
            self._json(403, {"error": "csrf_failed"})
            return
        try:
            data = self._body()
            if path == "/api/social/posts":
                scheduled = data.get("scheduled_at")
                post = STORE.enqueue(
                    platform=str(data.get("platform") or ""),
                    text=str(data.get("text") or ""),
                    scheduled_at=int(scheduled) if scheduled not in (None, "") else None,
                    media_url=str(data.get("media_url") or ""),
                    video_path=str(data.get("video_path") or ""),
                    metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
                    idempotency_key=str(data.get("idempotency_key") or ""),
                )
                self._json(201, {"post": post})
                return
            if path == "/api/social/settings":
                STORE.set_auto_mode(bool(data.get("auto_mode")))
                self._json(200, {"auto_mode": STORE.auto_mode()})
                return
            if path.startswith("/api/social/posts/"):
                parts = path.strip("/").split("/")
                if len(parts) != 5:
                    raise ValueError("bad_path")
                post_id = int(parts[3])
                action = parts[4]
                if action == "approve":
                    ok = STORE.approve(post_id)
                elif action == "cancel":
                    ok = STORE.cancel(post_id)
                elif action == "retry":
                    ok = STORE.retry(post_id)
                else:
                    raise ValueError("unsupported_action")
                self._json(200 if ok else 409, {"ok": ok})
                return
            self._json(404, {"error": "not_found"})
        except Exception as exc:
            self._json(400, {"error": str(exc)})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.host not in ("127.0.0.1", "localhost"):
        allow_lan = os.environ.get("AI_APP_ALLOW_LAN") == "1"
        admin_token = os.environ.get("SOCIAL_ADMIN_TOKEN", "").strip()
        if not allow_lan or not admin_token:
            raise SystemExit(
                "Refusing non-loopback bind unless AI_APP_ALLOW_LAN=1 and SOCIAL_ADMIN_TOKEN are set"
            )

    WORKER.start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print("SNS automation: http://" + args.host + ":" + str(args.port), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        WORKER.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

    @staticmethod
    def _index(spec: AppSpec) -> str:
        title = spec.project_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        requested = (spec.design_style or "modern").strip().lower()
        allowed = {"minimal", "premium", "modern", "friendly", "business", "soft", "finance", "youthful", "future", "dark"}
        theme = requested if requested in allowed else "youthful"
        if theme == "modern":
            theme = "youthful"
        return f'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{title}</title>
<link rel="stylesheet" href="styles.css">
<link rel="stylesheet" href="social.css">
</head>
<body data-theme="{theme}">
<header class="topbar"><div class="shell nav"><strong class="brand">{title}</strong><div class="nav-actions"><span class="status-badge"><span class="status-dot"></span>SNS Automation</span><button class="icon-button" id="themeToggle" type="button" aria-label="表示テーマを切り替える" title="テーマ: システム">◐</button></div></div></header>
<main class="shell">
<section class="hero"><div class="hero-copy"><span class="eyebrow">SOCIAL AUTOMATION</span><h1>投稿を予約して、自動で届ける。</h1><p>初期状態はDRY RUNです。認証情報は環境変数からのみ読み込み、コードや投稿DBには保存しません。</p></div></section>
<section class="stats-grid">
<div class="stat-card"><span>承認待ち</span><strong id="pendingCount">0</strong><small>件</small></div>
<div class="stat-card"><span>予約中</span><strong id="queuedCount">0</strong><small>件</small></div>
<div class="stat-card"><span>投稿済み</span><strong id="postedCount">0</strong><small>件</small></div>
</section>
<section class="panel">
<div class="section-heading"><div><span class="section-kicker">MODE</span><h2>投稿モード</h2></div><p id="modeDetail">確認中...</p></div>
<div class="button-row"><button id="toggleAuto">自動モードを切替</button><button class="secondary" id="refresh">再読み込み</button></div>
<p id="providerStatus" class="feedback" aria-live="polite"></p>
</section>
<section class="content-grid">
<section class="panel">
<div class="section-heading"><div><span class="section-kicker">NEW POST</span><h2>投稿を予約</h2></div><p>自動モードOFFでは承認後に投稿されます。</p></div>
<div class="form-grid">
<label>投稿先<select id="platform"><option value="threads">Threads</option><option value="x">X</option><option value="instagram">Instagram</option><option value="youtube">YouTube</option></select></label>
<label>予約日時<input id="scheduledAt" type="datetime-local"></label>
<label class="wide">本文 / 説明<textarea id="text" rows="6" placeholder="投稿内容"></textarea></label>
<label class="wide">Instagram用 公開メディアURL<input id="mediaUrl" placeholder="https://..."></label>
<label class="wide">YouTube用 動画ファイル名<input id="videoPath" placeholder="media/video.mp4 または video.mp4"></label>
<label class="wide">YouTubeタイトル<input id="videoTitle" placeholder="動画タイトル"></label>
</div>
<button id="queuePost" class="full-button">投稿を予約</button>
<p id="status" class="feedback" aria-live="polite"></p>
</section>
<section class="panel">
<div class="section-heading"><div><span class="section-kicker">QUEUE</span><h2>投稿キュー</h2></div><p>承認・取消・失敗時の再実行ができます。</p></div>
<ul id="itemList" class="clean-list"></ul>
<div id="emptyState" class="empty-state">投稿はまだありません。</div>
</section>
</section>
</main>
<div id="toast" class="toast" role="status" aria-live="polite" aria-atomic="true"></div>
<dialog id="confirmDialog" class="confirm-dialog"><form method="dialog"><div class="dialog-icon">?</div><h2>確認</h2><p id="confirmMessage">この操作を続けますか？</p><div class="dialog-actions"><button value="cancel" class="ghost">キャンセル</button><button value="ok">続ける</button></div></form></dialog>
<script src="app.js"></script>
</body>
</html>'''

    @staticmethod
    def _styles() -> str:
        return """textarea{width:100%;border:1px solid #D1D5DB;background:#FBFBFC;color:var(--color-text);padding:12px 14px;border-radius:var(--radius-sm);font:inherit;resize:vertical;min-height:130px}
textarea:focus-visible{outline:3px solid #A5B4FC;outline-offset:2px}
.clean-list li{align-items:flex-start;flex-wrap:wrap}.clean-list li>span{flex:1 1 320px;white-space:pre-wrap}.clean-list .button-row{margin-top:0}
#providerStatus{overflow-wrap:anywhere}.status-badge{white-space:nowrap}
@media(max-width:800px){.clean-list .button-row{width:100%}.clean-list .button-row button{flex:1}}
"""

    @staticmethod
    def _script() -> str:
        return r'''const statusNode=document.querySelector('#status');
const toast=document.querySelector('#toast');
const confirmDialog=document.querySelector('#confirmDialog');
const confirmMessage=document.querySelector('#confirmMessage');
const themeToggle=document.querySelector('#themeToggle');
const list=document.querySelector('#itemList');
const emptyState=document.querySelector('#emptyState');
const modeDetail=document.querySelector('#modeDetail');
const providerStatus=document.querySelector('#providerStatus');
let csrf='';
let autoMode=false;
let toastTimer=null;

function showToast(message,type='info'){
  if(!toast)return;
  toast.textContent=message;toast.dataset.type=type;toast.classList.add('show');
  clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove('show'),2600);
}
function confirmAction(message){
  if(!confirmDialog||typeof confirmDialog.showModal!=='function')return Promise.resolve(window.confirm(message));
  confirmMessage.textContent=message;
  return new Promise(resolve=>{
    const close=()=>{confirmDialog.removeEventListener('close',close);resolve(confirmDialog.returnValue==='ok');};
    confirmDialog.addEventListener('close',close);confirmDialog.showModal();
  });
}
function initTheme(){
  const saved=localStorage.getItem('color-mode')||'system';
  document.documentElement.dataset.colorMode=saved;
  if(themeToggle)themeToggle.title='テーマ: '+({system:'システム',light:'ライト',dark:'ダーク'}[saved]||'システム');
}
function cycleTheme(){
  const order=['system','light','dark'];
  const current=document.documentElement.dataset.colorMode||'system';
  const next=order[(order.indexOf(current)+1)%order.length];
  document.documentElement.dataset.colorMode=next;localStorage.setItem('color-mode',next);
  if(themeToggle)themeToggle.title='テーマ: '+({system:'システム',light:'ライト',dark:'ダーク'}[next]);
  showToast('表示テーマ: '+({system:'システム',light:'ライト',dark:'ダーク'}[next]));
}
if(themeToggle)themeToggle.addEventListener('click',cycleTheme);
initTheme();

async function api(path,options={}){
  options.headers={'Content-Type':'application/json',...(options.headers||{})};
  if(csrf)options.headers['X-CSRF-Token']=csrf;
  const response=await fetch(path,options);
  let data={};
  try{data=await response.json();}catch{}
  if(!response.ok)throw new Error(data.error||'request_failed');
  return data;
}

function fmt(ts){
  if(!ts)return '-';
  return new Date(Number(ts)*1000).toLocaleString();
}

function updateCounts(counts={}){
  document.querySelector('#pendingCount').textContent=String(counts.pending_approval||0);
  document.querySelector('#queuedCount').textContent=String((counts.queued||0)+(counts.retry||0));
  document.querySelector('#postedCount').textContent=String(counts.posted||0);
}

function render(posts){
  list.innerHTML='';
  emptyState.hidden=posts.length>0;
  for(const post of posts){
    const li=document.createElement('li');
    const info=document.createElement('span');
    info.textContent=post.platform.toUpperCase()+' · '+post.status+' · '+fmt(post.scheduled_at)+' · '+(post.text||post.video_path||post.media_url||'');
    const actions=document.createElement('div');
    actions.className='button-row';
    if(post.status==='pending_approval'){
      const approve=document.createElement('button');approve.textContent='承認';
      approve.onclick=()=>act(post.id,'approve');actions.append(approve);
    }
    if(['pending_approval','queued','retry'].includes(post.status)){
      const cancel=document.createElement('button');cancel.className='ghost';cancel.textContent='取消';
      cancel.onclick=async()=>{if(await confirmAction('この予約投稿を取り消しますか？'))await act(post.id,'cancel');};actions.append(cancel);
    }
    if(post.status==='failed'){
      const retry=document.createElement('button');retry.className='secondary';retry.textContent='再実行';
      retry.onclick=()=>act(post.id,'retry');actions.append(retry);
    }
    li.append(info,actions);list.append(li);
  }
}

async function bootstrap(){
  const data=await api('/api/social/bootstrap');
  csrf=data.csrf||'';
  autoMode=!!data.auto_mode;
  modeDetail.textContent=(data.credentials?.dry_run?'DRY RUN / ':'実投稿 / ')+(autoMode?'自動モードON':'承認モード');
  const c=data.credentials||{};
  providerStatus.textContent='接続状態: X '+(c.x?'OK':'未設定')+' / Threads '+(c.threads?'OK':'未設定')+' / Instagram '+(c.instagram?'OK':'未設定')+' / YouTube '+(c.youtube?'OK':'未設定');
  updateCounts(data.counts||{});
  await load();
}

async function load(){
  const data=await api('/api/social/posts');
  render(data.posts||[]);
  updateCounts(data.counts||{});
}

async function act(id,action){
  try{
    await api('/api/social/posts/'+id+'/'+action,{method:'POST',body:'{}'});
    statusNode.textContent='更新しました';
    showToast('更新しました','success');
    await load();
  }catch(e){statusNode.textContent=e.message;showToast(e.message,'error');}
}

document.querySelector('#toggleAuto').onclick=async()=>{
  try{
    const data=await api('/api/social/settings',{method:'POST',body:JSON.stringify({auto_mode:!autoMode})});
    autoMode=!!data.auto_mode;
    modeDetail.textContent=(modeDetail.textContent.split('/')[0]||'')+'/ '+(autoMode?'自動モードON':'承認モード');
    const message=autoMode?'自動投稿をONにしました':'承認モードに戻しました';
    statusNode.textContent=message;showToast(message,'success');
  }catch(e){statusNode.textContent=e.message;showToast(e.message,'error');}
};

document.querySelector('#refresh').onclick=()=>load().catch(e=>statusNode.textContent=e.message);

document.querySelector('#queuePost').onclick=async()=>{
  const platform=document.querySelector('#platform').value;
  const rawDate=document.querySelector('#scheduledAt').value;
  const text=document.querySelector('#text').value.trim();
  const mediaUrl=document.querySelector('#mediaUrl').value.trim();
  const videoPath=document.querySelector('#videoPath').value.trim();
  const title=document.querySelector('#videoTitle').value.trim();
  const scheduled_at=rawDate?Math.floor(new Date(rawDate).getTime()/1000):null;
  try{
    await api('/api/social/posts',{
      method:'POST',
      body:JSON.stringify({
        platform,text,media_url:mediaUrl,video_path:videoPath,scheduled_at,
        metadata:{title,description:text,privacyStatus:'private'}
      })
    });
    const message=autoMode?'予約しました':'承認待ちに追加しました';
    statusNode.textContent=message;showToast(message,'success');
    await load();
  }catch(e){statusNode.textContent=e.message;showToast(e.message,'error');}
};

bootstrap().catch(e=>{statusNode.textContent=e.message;showToast(e.message,'error');});
'''

    @staticmethod
    def _readme() -> str:
        return '''# SNS Automation Runtime

この生成物は、SNS投稿予約・承認・自動投稿・失敗リトライ・履歴管理を行うローカルファースト実装です。

## 安全な初期状態
- SOCIAL_DRY_RUN=1 相当が既定です。明示的に SOCIAL_DRY_RUN=0 を設定するまで外部投稿しません。
- 自動モードはOFFが既定です。OFFでは新規投稿は pending_approval になり、画面で承認するまで送信しません。
- APIトークンをソースコード、SQLite、設定JSONへ保存しません。環境変数からのみ読みます。
- LAN公開する場合は AI_APP_ALLOW_LAN=1 に加えて SOCIAL_ADMIN_TOKEN が必須です。

## 対応プロバイダ
- X: テキスト投稿 (X_ACCESS_TOKEN)
- Threads: テキスト投稿 (THREADS_USER_ID, THREADS_ACCESS_TOKEN)
- Instagram: 公開画像URL投稿 (INSTAGRAM_USER_ID, INSTAGRAM_ACCESS_TOKEN, META_GRAPH_API_BASE)
- YouTube: media/ 配下の動画アップロード (YOUTUBE_ACCESS_TOKEN)

各SNSのAPI要件・権限・審査・レート制限は変更されるため、実運用前に各社公式ドキュメントの最新版を確認してください。

## 実投稿へ切替
1. 各SNSの認証情報を環境変数に設定。
2. DRY RUNで投稿キュー・承認・履歴をテスト。
3. SOCIAL_DRY_RUN=0 に変更。
4. 最初は自動モードOFFのまま手動承認で実投稿を確認。
5. 問題がない場合のみ画面から自動モードON。

失敗は最大5回まで指数バックオフで再試行し、その後 failed で停止します。
'''
