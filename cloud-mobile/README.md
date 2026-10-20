# Ivy Mobile Studio — PC-independent intake + safe HTML preview (staging only)

This module is an **additive, mobile-first Cloudflare Workers + D1 PWA**.
The desktop Ivy/Tkinter and its existing local API remain unchanged.

## What works when the home PC is OFF
- iPhone / Android browser entry and Add to Home Screen (PWA shell).
- OWNER-only API guarded by verified Cloudflare Access JWT/native identity.
- Save app/web project requests to D1 with a daily cap of 10 and idempotency keys.
- See the last 30 saved requests and safely pause further intake.
- Read-only status makes clear the AI/code-generation worker is **not connected**.
- **Web-mode only:** OWNER can explicitly compile a bounded, deterministic, **non-AI static HTML** preview from a saved request, inspect the HTML in a fully sandboxed iframe, and download the generated single HTML file.
- Preview output and a small checklist are stored in a new D1 table by migration 0002; one transaction prevents duplicate artifacts and races with stop/cancel actions.
- A pending request can be cancelled (no deletion); emergency pause stops new intake and new preview compilation, preserving saved data.

## What does NOT work yet
- No hosted AI inference, **AI-based** code creation, arbitrary-code execution, test-and-repair loop, APK/iOS/Windows binary build, or publishing.
- Static template generation is **not** a functioning custom application, LLM-created source code, or isolated user-code test.
- No AI worker dispatcher, GitHub Actions production runner, cloud project file manager, user chat history, or installer package is connected yet.
- Saving a request is not execution. All new requests use status `awaiting_hosted_worker`; OWNER can later trigger `template_ready` for **static web templates only**.
- PC-local projects, SQLite files, Ollama and credentials do not sync to the cloud.
- No production deployment or live Cloudflare account test has been performed.

## Owner-only staging setup (on mobile browser or GitHub Codespaces)
1. Create a **new staging** Cloudflare D1 database: `ivy-mobile-intake-staging`.
2. In `cloud-mobile/`, copy `wrangler.example.jsonc` to `wrangler.jsonc` (ignored if configured).
3. Replace D1 database_id with the newly created staging DB ID.
4. Configure Cloudflare Access app policy for only OWNER email and protect **the whole Worker** (including assets), not just API paths.
5. Set `TEAM_DOMAIN` (your `https://team.cloudflareaccess.com` URL), `ACCESS_AUD` (Access application AUD), and `OWNER_EMAIL`; these must match exactly.
6. Run `npm run check && npm test`.
7. Run `npx wrangler d1 migrations apply ivy-mobile-intake-staging --remote --config wrangler.jsonc` after reviewing **0001 and 0002** SQL. This is staging only.
8. Deploy to **a new staging Worker name**, never overwrite Ivy or AI Company production: `npx wrangler deploy --config wrangler.jsonc`.
9. Confirm Access denies unsigned/API requests; log in as OWNER; verify status, save, duplicate retry, history, static preview generation, sandbox isolation, HTML download, cancellation and emergency stop on smartphone.
10. Initial D1 state is `paused=1` (fail closed). To enable intake **after testing Access**, deliberately update the staging control row to `paused=0`. Do not enable inference; none is implemented.

Never commit a real owner email, audience, tokens, secrets, raw runtime database, or private prompts. No Cloudflare tokens are needed inside app source; use platform-protected deployment credentials. Respect Cloudflare/GitHub free-tier limits.

## Design boundary
This module is separate because the existing Python service is a full, stateful local build engine. Exposing it over the public internet or forwarding bearer tokens from a browser would be unsafe. A future hosted worker will require a separate authenticated command queue, persistent isolated build storage, job budgets, approval gates, and audit logs before it can safely perform real generation.

## Phase 2 static preview lifecycle (code implemented, not deployed)

```
PWA (Access OWNER) → D1 saved request → confirm static template preview
                   → Cloudflare Worker compiles known HTML + checks
                   → D1 immutable artifact (one per request)
                   → same-origin sandbox iframe + HTML attachment download
```

The Worker NEVER runs user-supplied HTML/JS as executable code. It escapes the
prompt for inclusion in a fixed static page, validates output size and basic
structure, and serves preview with `Content-Security-Policy: sandbox`,
`script-src 'none'`, `connect-src 'none'` and `form-action 'none'`.
The iframe also sets `sandbox=""`. The HTML file may be opened locally
for inspection, but it is not yet a generated, feature-complete app.
The `app` target currently records requests only.

API extensions (all protected by OWNER authentication + verified same-origin
JSON POST; no API key in browser):
- `POST /api/v1/requests/{uuid}/build-preview` with
  `{"confirm":"generate_static_template"}` (explicit OWNER action).
- `GET /api/v1/requests/{uuid}/preview` (no script execution).
- `GET /api/v1/requests/{uuid}/download` (single HTML attachment).
- `POST /api/v1/requests/{uuid}/cancel` with
  `{"confirm":"cancel_pending"}`.
- Existing `POST /api/v1/stop` also prevents new preview builds.
- API status explicitly returns `ai_generation_enabled:false`,
  `hosted_worker_connected:false`, `static_preview_enabled:true`.

After rollout, verify data isolation with two distinct Access identities,
including that an unauthorized user cannot see/download another OWNER's
generated file. The Access application should be configured to allow
only the designated OWNER identity.

## What is needed before claiming full mobile cloud AI development

1. Isolated short-lived build executors (GitHub Actions or a dedicated
   sandbox service) with strict time, memory, network and command boundaries.
   Never execute an LLM-produced shell script inside a public Worker.
2. Explicitly connected inference provider or hosted model with a configured
   zero-or-capped budget, owner-specific credentials, token accounting and
   fail-closed behavior when unavailable. Local Ollama is unavailable with
   the PC powered off.
3. Durable job-lease/idempotency protocol, worker-to-D1 authentication,
   artifacts with checksums, code generation trace, reproducible tests,
   scan results, retry ceilings, kill switch and owner approval.
4. Actual React/Web preview of produced files, revisions and OWNER-mediated
   release, followed by separate Android/iOS build infrastructure.
5. Staging Cloudflare Access/D1 deployment, smartphone E2E tests with
   the home PC OFF, and real observation of free-tier spend/quotas.

**No staged URL exists until the owner explicitly deploys a new staging
Worker and completes Cloudflare Access + D1 setup.** This PR does not
alter production, merge source branches, register paid APIs, or perform
any remote deployment. CI proves code behavior on runners, not end-to-end
Cloudflare account configuration or 24-hour availability.
