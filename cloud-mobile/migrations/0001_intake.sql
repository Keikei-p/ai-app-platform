-- Staging-only Ivy mobile intake; no autonomous execution triggers.
CREATE TABLE IF NOT EXISTS ivy_control (
  id INTEGER PRIMARY KEY CHECK (id=1),
  paused INTEGER NOT NULL DEFAULT 1 CHECK (paused IN (0,1)),
  updated_at INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO ivy_control (id,paused,updated_at) VALUES (1,1,0);

CREATE TABLE IF NOT EXISTS ivy_requests (
  id TEXT PRIMARY KEY,
  owner_email TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  mode TEXT NOT NULL CHECK(mode IN ('app','web')),
  prompt TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'awaiting_hosted_worker',
  created_at INTEGER NOT NULL,
  UNIQUE(owner_email,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_ivy_requests_owner ON ivy_requests(owner_email,created_at DESC);
