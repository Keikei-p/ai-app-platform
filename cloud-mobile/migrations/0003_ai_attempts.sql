-- Future, opt-in Cloudflare Workers AI: 1 attempt per OWNER per UTC day.
-- Failures also consume the quota to prevent paid retry storms.
CREATE TABLE IF NOT EXISTS ivy_ai_attempts (
  request_id TEXT PRIMARY KEY REFERENCES ivy_requests(id),
  owner_email TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('reserved','succeeded','failed')),
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ivy_ai_attempts_owner_day
  ON ivy_ai_attempts(owner_email,created_at DESC);
