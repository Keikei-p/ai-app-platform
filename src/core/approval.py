from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import secrets
from .database import connect, utc_now, log_event

APPROVAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS approval_requests (
  request_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  action TEXT NOT NULL,
  project_slug TEXT,
  status TEXT NOT NULL,
  approved_by TEXT
);
"""

@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    action: str
    project_slug: str | None
    expires_at: str

class ApprovalStore:
    def _ensure(self) -> None:
        with connect() as conn:
            conn.executescript(APPROVAL_SCHEMA)

    def create(self, action: str, project_slug: str | None, minutes: int = 15) -> ApprovalRequest:
        self._ensure()
        request_id = secrets.token_urlsafe(18)
        expires = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
        with connect() as conn:
            conn.execute("INSERT INTO approval_requests VALUES(?,?,?,?,?,?,?)", (request_id, utc_now(), expires, action, project_slug, "pending", None))
        log_event("approval.requested", action, project_slug, "permission-engine")
        return ApprovalRequest(request_id, action, project_slug, expires)

    def approve(self, request_id: str, actor: str) -> bool:
        self._ensure()
        now = datetime.now(timezone.utc)
        with connect() as conn:
            row = conn.execute("SELECT * FROM approval_requests WHERE request_id=?", (request_id,)).fetchone()
            if not row or row["status"] != "pending" or datetime.fromisoformat(row["expires_at"]) < now:
                return False
            conn.execute("UPDATE approval_requests SET status='approved',approved_by=? WHERE request_id=?", (actor, request_id))
        log_event("approval.approved", request_id, row["project_slug"], actor)
        return True

    def consume(self, request_id: str, action: str, project_slug: str | None) -> bool:
        self._ensure()
        now = datetime.now(timezone.utc)
        with connect() as conn:
            row = conn.execute("SELECT * FROM approval_requests WHERE request_id=?", (request_id,)).fetchone()
            if not row or row["status"] != "approved":
                return False
            if row["action"] != action or row["project_slug"] != project_slug or datetime.fromisoformat(row["expires_at"]) < now:
                return False
            conn.execute("UPDATE approval_requests SET status='consumed' WHERE request_id=?", (request_id,))
        log_event("approval.consumed", request_id, project_slug, "permission-engine")
        return True
