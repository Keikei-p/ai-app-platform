import { authorizeOwner } from "./owner-auth.mjs";

const LIMIT_PER_DAY = 10;
const HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "private, no-store",
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
  "referrer-policy": "no-referrer",
};
const reply = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: HEADERS });
const utcDay = () => Math.floor(Date.now() / 86400000) * 86400;

function sameOriginJson(request) {
  const url = new URL(request.url);
  const origin = request.headers.get("origin");
  const site = request.headers.get("sec-fetch-site");
  if (origin !== url.origin || (site && site !== "same-origin") ||
      !(request.headers.get("content-type") || "").toLowerCase().startsWith("application/json")) {
    throw new Error("invalid_origin");
  }
}
function validateRequest(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("invalid_body");
  const prompt = typeof value.prompt === "string" ? value.prompt.trim() : "";
  const mode = value.mode;
  const key = value.idempotency_key;
  if (!prompt || prompt.length > 1200) throw new Error("invalid_prompt");
  if (mode !== "web" && mode !== "app") throw new Error("invalid_mode");
  if (typeof key !== "string" || !/^[A-Za-z0-9_-]{16,80}$/.test(key)) throw new Error("invalid_key");
  return { prompt, mode, key };
}
async function readBody(request) {
  const length = Number(request.headers.get("content-length") || 0);
  if (length > 8192) throw new Error("request_too_large");
  const raw = await request.text();
  if (raw.length > 8192) throw new Error("request_too_large");
  return JSON.parse(raw);
}
async function staticAsset(request, assets) {
  if (!assets?.fetch) return reply({ ok: false, error: "assets_not_configured" }, 503);
  const source = await assets.fetch(request);
  const headers = new Headers(source.headers);
  headers.set("cache-control", "private, no-store");
  headers.set("x-content-type-options", "nosniff");
  headers.set("referrer-policy", "no-referrer");
  headers.set("x-frame-options", "DENY");
  headers.set("content-security-policy",
    "default-src 'none'; connect-src 'self'; script-src 'self'; style-src 'self'; " +
    "img-src 'self'; manifest-src 'self'; base-uri 'none'; object-src 'none'; " +
    "form-action 'self'; frame-ancestors 'none'");
  return new Response(source.body, { status: source.status, statusText: source.statusText, headers });
}
export async function handleRequest(request, env, ownerAuth = authorizeOwner, ctx) {
  const pathname = new URL(request.url).pathname;
  if (!pathname.startsWith("/api/v1/")) {
    if (request.method !== "GET" && request.method !== "HEAD")
      return reply({ ok: false, error: "method_not_allowed" }, 405);
    return staticAsset(request, env?.ASSETS);
  }
  let owner;
  try {
    owner = await ownerAuth(request, env, ctx);
    if (!owner || owner.role !== "owner" || !owner.email) throw new Error("not_owner");
  } catch {
    return reply({ ok: false, error: "owner_login_required" }, 403);
  }
  if (!env?.DB) return reply({ ok: false, error: "database_not_configured" }, 503);
  const db = env.DB;
  try {
    if (request.method === "GET" && pathname === "/api/v1/status") {
      const [control, totals] = await Promise.all([
        db.prepare("SELECT paused FROM ivy_control WHERE id=1").first(),
        db.prepare("SELECT COUNT(*) AS today FROM ivy_requests WHERE owner_email=? AND created_at>=?")
          .bind(owner.email, utcDay()).first(),
      ]);
      return reply({
        ok: true, mode: "cloud_intake_only", hosted_worker_connected: false,
        generation_enabled: false, publishing_enabled: false,
        paused: control?.paused !== 0, requests_today: Number(totals?.today || 0),
        daily_limit: LIMIT_PER_DAY,
        note: "依頼の保存・確認のみ。コード生成と自動公開は未接続です。",
      });
    }
    if (request.method === "GET" && pathname === "/api/v1/requests") {
      const result = await db.prepare(
        "SELECT id,mode,prompt,status,created_at FROM ivy_requests WHERE owner_email=? " +
        "ORDER BY created_at DESC, id DESC LIMIT 30"
      ).bind(owner.email).all();
      return reply({ ok: true, requests: result.results || [] });
    }
    if (request.method === "POST" && pathname === "/api/v1/requests") {
      sameOriginJson(request);
      const { prompt, mode, key } = validateRequest(await readBody(request));
      const existing = await db.prepare(
        "SELECT id,prompt,mode,status FROM ivy_requests WHERE owner_email=? AND idempotency_key=?"
      ).bind(owner.email, key).first();
      if (existing) {
        if (existing.prompt !== prompt || existing.mode !== mode)
          return reply({ ok: false, error: "idempotency_conflict" }, 409);
        return reply({ ok: true, saved: true, reused: true, request_id: existing.id, status: existing.status });
      }
      const control = await db.prepare("SELECT paused FROM ivy_control WHERE id=1").first();
      if (!control || control.paused !== 0) return reply({ ok: false, error: "paused" }, 423);
      const id = crypto.randomUUID();
      const added = await db.prepare(
        "INSERT INTO ivy_requests (id,owner_email,idempotency_key,mode,prompt,status,created_at) " +
        "SELECT ?,?,?,?,?,'awaiting_hosted_worker',? WHERE " +
        "(SELECT COUNT(*) FROM ivy_requests WHERE owner_email=? AND created_at>=?)<? " +
        "AND (SELECT paused FROM ivy_control WHERE id=1)=0"
      ).bind(id,owner.email,key,mode,prompt,Math.floor(Date.now()/1000),owner.email,utcDay(),LIMIT_PER_DAY).run();
      if (!added.meta?.changes) return reply({ ok: false, error: "daily_limit_or_paused" }, 429);
      return reply({ ok: true, saved: true, reused: false, request_id: id,
        status: "awaiting_hosted_worker" }, 202);
    }
    if (request.method === "POST" && pathname === "/api/v1/stop") {
      sameOriginJson(request);
      const body = await readBody(request);
      if (!body || typeof body !== "object" || Array.isArray(body))
        throw new Error("invalid_body");
      await db.prepare("UPDATE ivy_control SET paused=1,updated_at=? WHERE id=1")
        .bind(Math.floor(Date.now()/1000)).run();
      return reply({ ok:true, paused:true });
    }
    return reply({ ok: false, error: "not_found" }, 404);
  } catch (error) {
    if (error instanceof SyntaxError || [
      "invalid_origin","invalid_body","invalid_prompt","invalid_mode",
      "invalid_key","request_too_large"
    ].includes(error?.message)) return reply({ ok: false, error: "invalid_request" }, 400);
    if (error?.message && /UNIQUE constraint failed/.test(error.message))
      return reply({ ok:false, error:"duplicate_submission_retry_with_same_id" }, 409);
    return reply({ ok: false, error: "temporarily_unavailable" }, 503);
  }
}
export default { fetch(request, env, ctx) { return handleRequest(request, env, authorizeOwner, ctx); } };
