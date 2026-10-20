/**
 * Cloudflare Access JWT verification for OWNER-only Ivy mobile cloud intake.
 * Never trust a forwarded email/header without cryptographic RS256 verification.
 * Does not copy the Windows auth.db or disclose credentials in the frontend.
 */
let cachedKeys = null;
let cachedDomain = "";
let keysExpiry = 0;

function strictDomain(raw) {
  if (typeof raw !== "string" || !raw) throw new Error("access_not_configured");
  const parsed = new URL(raw);
  if (parsed.protocol !== "https:" ||
      !/^[a-z0-9-]+\.cloudflareaccess\.com$/.test(parsed.hostname) ||
      parsed.username || parsed.password || parsed.port || parsed.pathname !== "/" ||
      parsed.search || parsed.hash) {
    throw new Error("invalid_access_team_domain");
  }
  return parsed.origin;
}
function decodeB64Url(src) {
  if (!/^[A-Za-z0-9_-]+$/.test(src) || src.length > 12000) throw new Error("invalid_token");
  const raw = atob(src.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(src.length / 4) * 4, "="));
  return Uint8Array.from(raw, c => c.charCodeAt(0));
}
function parsedJson(bytes) {
  const result = JSON.parse(new TextDecoder().decode(bytes));
  if (!result || typeof result !== "object" || Array.isArray(result)) throw new Error("invalid_token");
  return result;
}
async function loadKeys(teamDomain) {
  const now = Date.now();
  if (cachedKeys && cachedDomain === teamDomain && now < keysExpiry) return cachedKeys;
  const response = await fetch(teamDomain + "/cdn-cgi/access/certs", {
    headers: { "accept": "application/json" },
    signal: AbortSignal.timeout(4000),
  });
  if (!response.ok) throw new Error("access_cert_unavailable");
  const text = await response.text();
  if (text.length > 60000) throw new Error("cert_oversize");
  const data = JSON.parse(text);
  if (!Array.isArray(data.keys)) throw new Error("cert_invalid");
  const keys = data.keys.filter(k => k && k.kty === "RSA" && k.alg === "RS256" &&
    k.use === "sig" && typeof k.kid === "string" && typeof k.n === "string" && typeof k.e === "string");
  if (!keys.length) throw new Error("cert_invalid");
  cachedKeys = keys;
  cachedDomain = teamDomain;
  keysExpiry = now + 5 * 60 * 1000;
  return keys;
}
export async function authorizeOwner(request, env, ctx) {
  if (!env?.ACCESS_AUD || !env?.OWNER_EMAIL) throw new Error("access_not_configured");

  // Native Worker-level Access identity is provided by Cloudflare after its
  // own policy/authentication check. It remains available even where the
  // legacy cf-access-jwt-assertion request header cannot be read.
  // Never use plain user-controlled headers, query params, or cookies instead.
  if (ctx?.access) {
    if (ctx.access.aud !== env.ACCESS_AUD)
      throw new Error("access_native_audience_mismatch");
    if (typeof ctx.access.getIdentity !== "function")
      throw new Error("access_native_identity_unavailable");
    let identity;
    try { identity = await ctx.access.getIdentity(); }
    catch { throw new Error("access_native_identity_unavailable"); }
    if (typeof identity?.email !== "string" ||
        identity.email.trim().toLowerCase() !== env.OWNER_EMAIL.trim().toLowerCase())
      throw new Error("access_native_owner_mismatch");
    return { email: identity.email.trim().toLowerCase(), role: "owner" };
  }

  // Compatibility for deployments which don't expose ctx.access. Continue
  // cryptographically verifying the Access JWT (never trust raw email).
  const issuer = strictDomain(env.TEAM_DOMAIN);
  const jwt = request.headers.get("cf-access-jwt-assertion");
  if (!jwt) throw new Error("access_denied_missing_assertion");
  if (jwt.length > 20000) throw new Error("access_denied");
  const parts = jwt.split(".");
  if (parts.length !== 3) throw new Error("access_denied");
  const header = parsedJson(decodeB64Url(parts[0]));
  const payload = parsedJson(decodeB64Url(parts[1]));
  if (header.alg !== "RS256" || typeof header.kid !== "string" || header.typ && header.typ !== "JWT") {
    throw new Error("access_denied");
  }
  const now = Math.floor(Date.now() / 1000);
  if (payload.iss !== issuer ||
      !(Array.isArray(payload.aud) ? payload.aud.includes(env.ACCESS_AUD) : payload.aud === env.ACCESS_AUD) ||
      typeof payload.exp !== "number" || payload.exp <= now ||
      typeof payload.iat !== "number" || payload.iat > now + 60 ||
      (typeof payload.nbf === "number" && payload.nbf > now + 60) ||
      typeof payload.email !== "string" ||
      payload.email.trim().toLowerCase() !== env.OWNER_EMAIL.trim().toLowerCase()) {
    throw new Error("access_denied");
  }
  const keys = await loadKeys(issuer);
  const keyData = keys.find(k => k.kid === header.kid);
  if (!keyData) throw new Error("access_denied");
  const key = await crypto.subtle.importKey("jwk", keyData,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  const valid = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, decodeB64Url(parts[2]),
    new TextEncoder().encode(parts[0] + "." + parts[1]));
  if (!valid) throw new Error("access_denied");
  return { email: payload.email.trim().toLowerCase(), role: "owner" };
}
