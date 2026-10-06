from __future__ import annotations
import sqlite3
from contextlib import contextmanager
from typing import Iterator
from datetime import datetime, timezone
from .config import DB_PATH, WORKSPACE_DIR
from .redaction import redact_sensitive

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  event_type TEXT NOT NULL,
  project_slug TEXT,
  actor TEXT NOT NULL,
  details TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  project_slug TEXT,
  instruction TEXT NOT NULL,
  status TEXT NOT NULL,
  result TEXT
);
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  action TEXT NOT NULL,
  project_slug TEXT,
  status TEXT NOT NULL,
  actor TEXT NOT NULL,
  details TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS remote_commands (
  command_id TEXT PRIMARY KEY,
  received_at TEXT NOT NULL,
  action TEXT NOT NULL,
  project_slug TEXT,
  status TEXT NOT NULL,
  details TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS maintenance_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  project_slug TEXT NOT NULL,
  severity TEXT NOT NULL,
  code TEXT NOT NULL,
  message TEXT NOT NULL
);
"""

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db() -> None:
    with connect():
        pass
    _sync_projects_from_workspace()

def _sync_projects_from_workspace() -> None:
    """Recover project index rows from durable project.json files.

    This makes the workspace the recoverable source of truth if a database was
    recreated or an older dev-mode project was migrated into persistent storage.
    """
    import json
    for project_dir in WORKSPACE_DIR.iterdir():
        if not project_dir.is_dir() or project_dir.name.startswith("."):
            continue
        meta_path = project_dir / "project.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            name = str(meta.get("name") or project_dir.name).strip()
            slug = str(meta.get("slug") or project_dir.name).strip()
            if name and slug == project_dir.name:
                upsert_project(name, slug)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue

def log_event(event_type: str, details: str, project_slug: str | None = None, actor: str = "local-user") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit_log(created_at,event_type,project_slug,actor,details) VALUES(?,?,?,?,?)",
            (utc_now(), event_type, project_slug, actor, redact_sensitive(details)),
        )

def list_audit(limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

def list_projects() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]

def upsert_project(name: str, slug: str) -> None:
    now = utc_now()
    with connect() as conn:
        conn.execute(
            """INSERT INTO projects(name,slug,created_at,updated_at) VALUES(?,?,?,?)
               ON CONFLICT(slug) DO UPDATE SET name=excluded.name,updated_at=excluded.updated_at""",
            (name, slug, now, now),
        )

def create_job(project_slug: str | None, instruction: str) -> int:
    now = utc_now()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO jobs(created_at,updated_at,project_slug,instruction,status,result) VALUES(?,?,?,?,?,?)",
            (now, now, project_slug, redact_sensitive(instruction), "running", None),
        )
        return int(cur.lastrowid)

def finish_job(job_id: int, status: str, result: str) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE jobs SET updated_at=?,status=?,result=? WHERE id=?",
            (utc_now(), status, redact_sensitive(result), job_id),
        )

def save_remote_command(command_id: str, action: str, project_slug: str | None, status: str, details: str) -> bool:
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO remote_commands(command_id,received_at,action,project_slug,status,details) VALUES(?,?,?,?,?,?)",
                (command_id, utc_now(), action, project_slug, status, redact_sensitive(details)),
            )
        return True
    except sqlite3.IntegrityError:
        return False

def save_maintenance_report(project_slug: str, severity: str, code: str, message: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO maintenance_reports(created_at,project_slug,severity,code,message) VALUES(?,?,?,?,?)",
            (utc_now(), project_slug, severity, code, redact_sensitive(message)),
        )

def delete_project_record(slug: str) -> None:
    """Internal/test cleanup helper; does not delete project files."""
    with connect() as conn:
        conn.execute("DELETE FROM projects WHERE slug=?", (slug,))
