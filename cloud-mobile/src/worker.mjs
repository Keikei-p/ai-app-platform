import { authorizeOwner } from "./owner-auth.mjs";
import { compileStaticPreview, GENERATOR_KIND } from "./static-preview.mjs";
import { chooseTemplate, compileInteractiveTemplate } from "./interactive-template.mjs";

const LIMIT_PER_DAY = 10;
const REQUEST_ACTION = /^\/api\/v1\/requests\/([a-f0-9-]{36})\/(build-preview|preview|download|cancel)$/i;
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
    // Only this fixed, escaped HTML template executes in a Worker.
    // An LLM/sandboxed build runner is NOT present, and is never implied.
    const action = pathname.match(REQUEST_ACTION);
    if (action) {
      const id = action[1];
      const operation = action[2];
      const record = await db.prepare(
        "SELECT id,mode,prompt,status FROM ivy_requests WHERE id=? AND owner_email=?"
      ).bind(id, owner.email).first();
      if (!record) return reply({ok:false,error:"not_found"},404);
      if (request.method === "GET" && ["preview","download"].includes(operation)) {
        const artifact = await db.prepare(
          "SELECT generator,html,checks_json FROM ivy_static_previews " +
          "WHERE request_id=? AND owner_email=?"
        ).bind(id, owner.email).first();
        if (!artifact || record.status !== "template_ready")
          return reply({ok:false,error:"preview_not_ready"},404);
        const headers = new Headers({
          "content-type": "text/html; charset=utf-8",
          "cache-control": "private, no-store",
          "x-content-type-options": "nosniff",
          "referrer-policy": "no-referrer",
          "content-security-policy": "sandbox" + (artifact.html.startsWith("<!doctype html>\n<!-- ivy-trusted-interactive-template:") ? " allow-scripts" : "") +
            "; default-src 'none'; style-src 'unsafe-inline'; " +
            (artifact.html.startsWith("<!doctype html>\n<!-- ivy-trusted-interactive-template:") ? "script-src 'unsafe-inline'" : "script-src 'none'") +
            "; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'",
        });
        if (operation === "download")
          headers.set("content-disposition", 'attachment; filename="ivy-static-preview.html"');
        return new Response(artifact.html, {status:200,headers});
      }
      if (request.method === "POST" && operation === "cancel") {
        sameOriginJson(request);
        const body = await readBody(request);
        if (body?.confirm !== "cancel_pending") return reply({ok:false,error:"confirmation_required"},400);
        const result = await db.prepare(
          "UPDATE ivy_requests SET status='cancelled' " +
          "WHERE id=? AND owner_email=? AND status='awaiting_hosted_worker'"
        ).bind(id,owner.email).run();
        if (!result.meta?.changes)
          return reply({ok:false,error:"cannot_cancel_finished_or_changed_request"},409);
        return reply({ok:true,request_id:id,status:"cancelled"});
      }
      if (request.method === "POST" && operation === "build-preview") {
        sameOriginJson(request);
        const body = await readBody(request);
        if (body?.confirm !== "generate_static_template")
          return reply({ok:false,error:"explicit_approval_required"},400);
        if (record.mode !== "web") return reply({ok:false,error:"web_template_only"},409);
        if (record.status === "template_ready")
          return reply({ok:true,reused:true,request_id:id,status:"template_ready",generator:GENERATOR_KIND});
        if (record.status !== "awaiting_hosted_worker")
          return reply({ok:false,error:"request_not_pending"},409);
        const selected = chooseTemplate(record.prompt, body.template || "auto");
        const {html,checks,generator,template_kind} = selected === "landing"
          ? {...compileStaticPreview(record),template_kind:"landing"}
          : compileInteractiveTemplate(record,selected);
        // One atomic D1 batch: preview + status transition. The SQL WHERE
        // clauses gate cancelled requests, another worker, and emergency pause.
        const [created,marked] = await db.batch([
          db.prepare(
            "INSERT OR IGNORE INTO ivy_static_previews " +
            "(request_id,owner_email,generator,html,checks_json,created_at) " +
            "SELECT id,owner_email,?,?,?,? FROM ivy_requests " +
            "WHERE id=? AND owner_email=? AND status='awaiting_hosted_worker' AND mode='web' " +
            "AND EXISTS(SELECT 1 FROM ivy_control WHERE id=1 AND paused=0)"
          ).bind(generator,html,JSON.stringify(checks),Math.floor(Date.now()/1000),id,owner.email),
          db.prepare(
            "UPDATE ivy_requests SET status='template_ready' " +
            "WHERE id=? AND owner_email=? AND status='awaiting_hosted_worker' " +
            "AND EXISTS(SELECT 1 FROM ivy_static_previews " +
            "WHERE ivy_static_previews.request_id=ivy_requests.id " +
            "AND ivy_static_previews.owner_email=ivy_requests.owner_email)"
          ).bind(id,owner.email)
        ]);
        if (!marked.meta?.changes) {
          const latest = await db.prepare(
            "SELECT status FROM ivy_requests WHERE id=? AND owner_email=?"
          ).bind(id,owner.email).first();
          if (latest?.status === "template_ready")
            return reply({ok:true,reused:true,request_id:id,status:"template_ready",generator});
          return reply({ok:false,error:"paused_or_request_changed"},409);
        }
        return reply({ok:true,reused:false,request_id:id,status:"template_ready",
          generator,template_kind,checks,ai_generated:false,tests:"template_integrity_only"},201);
      }
      return reply({ok:false,error:"method_not_allowed"},405);
    }
    if (request.method === "GET" && pathname === "/api/v1/status") {
      const [control, totals] = await Promise.all([
        db.prepare("SELECT paused FROM ivy_control WHERE id=1").first(),
        db.prepare("SELECT COUNT(*) AS today FROM ivy_requests WHERE owner_email=? AND created_at>=?")
          .bind(owner.email, utcDay()).first(),
      ]);
      return reply({
        ok: true, mode: "cloud_intake_with_static_preview", hosted_worker_connected: false,
        generation_enabled: false, ai_generation_enabled: false,
        static_preview_enabled: true, publishing_enabled: false,
        paused: control?.paused !== 0, requests_today: Number(totals?.today || 0),
        daily_limit: LIMIT_PER_DAY,
        note: "Web依頼の固定HTMLテンプレート生成・プレビューに対応。AIコード生成、ビルド、公開は未接続です。",
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
      "invalid_key","request_too_large","unsupported_preview_request",
      "preview_validation_failed","invalid_template","invalid_template_request","template_validation_failed"
    ].includes(error?.message)) return reply({ ok: false, error: "invalid_request" }, 400);
    if (error?.message && /UNIQUE constraint failed/.test(error.message))
      return reply({ ok:false, error:"duplicate_submission_retry_with_same_id" }, 409);
    return reply({ ok: false, error: "temporarily_unavailable" }, 503);
  }
}
export default { fetch(request, env, ctx) { return handleRequest(request, env, authorizeOwner, ctx); } };
