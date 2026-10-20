-- Phase 2: bounded static preview artifacts, NOT AI generated code.
-- Original intake rows are retained; existing OWNER data remains unchanged.
CREATE TABLE IF NOT EXISTS ivy_static_previews (
  request_id TEXT PRIMARY KEY REFERENCES ivy_requests(id),
  owner_email TEXT NOT NULL,
  generator TEXT NOT NULL CHECK(generator='static_template_v1'),
  html TEXT NOT NULL CHECK(length(html) <= 20000),
  checks_json TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ivy_previews_owner ON ivy_static_previews(owner_email,created_at DESC);
