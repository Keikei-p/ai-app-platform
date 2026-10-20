import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = filename => readFileSync(new URL(filename, import.meta.url),"utf8");
function readExampleConfig() {
  const src=read("../wrangler.example.jsonc");
  // The project uses only full-line JSONC comments. Reject trailing comments
  // so a broken joined comment cannot silently remove D1 configuration.
  const lines=src.split(/\r?\n/);
  const removed=lines.filter(line=>!/^\s*\/\//.test(line));
  assert.ok(removed.some(line=>/^\s*"d1_databases"\s*:/.test(line)),
    "D1 binding must be an active JSON key, not swallowed by a comment");
  return JSON.parse(removed.join("\n"));
}

test("Wrangler example parses and preserves the mandatory D1 binding",()=>{
  const c=readExampleConfig();
  assert.equal(c.name,"ivy-mobile-intake-staging");
  assert.equal(c.workers_dev,false);
  assert.equal(c.assets.directory,"./web");
  assert.equal(c.assets.binding,"ASSETS");
  assert.equal(c.assets.run_worker_first,true);
  assert.equal(c.main,"src/worker.mjs");
  assert.equal(c.d1_databases?.length,1);
  assert.equal(c.d1_databases[0].binding,"DB");
  assert.equal(c.d1_databases[0].migrations_dir,"./migrations");
  assert.equal(c.d1_databases[0].database_name,"ivy-mobile-intake-staging");
});

test("staging never enables billable AI or intake resume on first deploy",()=>{
  const c=readExampleConfig();
  assert.equal(c.vars.AI_DESIGN_ENABLED,"false");
  assert.equal(c.vars.AI_BUDGET_OWNER_APPROVED,"false");
  assert.equal(c.vars.ENABLE_OWNER_RESUME,"false");
  assert.equal(c.ai,undefined);
  assert.match(c.vars.ACCESS_AUD,/^REPLACE_/);
  assert.match(c.vars.OWNER_EMAIL,/example\.com$/);
  assert.match(c.d1_databases[0].database_id,/^REPLACE_/);
});

test("Cloudflare-only source remains isolated from main Ivy and production configs",()=>{
  const workflow=read("../../.github/workflows/ivy-mobile-cloud.yml");
  assert.match(workflow,/pull_request:/);
  assert.match(workflow,/cloud-mobile\/\*\*/);
  assert.doesNotMatch(workflow,/wrangler deploy|d1 migrations apply .*--remote|github\.com\/.*\/releases/);
  for(const file of ["0001_intake.sql","0002_static_previews.sql","0003_ai_attempts.sql"]){
    assert.match(read("../migrations/"+file),/CREATE TABLE IF NOT EXISTS/);
  }
});
