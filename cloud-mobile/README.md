# Ivy Mobile Studio — PC-independent request intake (staging only)

This module is an **additive, mobile-first Cloudflare Workers + D1 PWA**.
The desktop Ivy/Tkinter and its existing local API remain unchanged.

## What works when the home PC is OFF
- iPhone / Android browser entry and Add to Home Screen (PWA shell).
- OWNER-only API guarded by verified Cloudflare Access JWT/native identity.
- Save app/web project requests to D1 with a daily cap of 10 and idempotency keys.
- See the last 30 saved requests and safely pause further intake.
- Read-only status makes clear the actual generation worker is **not connected**.

## What does NOT work yet
- No hosted AI inference, code creation, testing, preview, APK generation, or publishing.
- Saving a request is not execution. All new requests use status \`awaiting_hosted_worker\`.
- PC-local projects, SQLite files, Ollama and credentials do not sync to the cloud.
- No production deployment or live Cloudflare account test has been performed.

## Owner-only staging setup (on mobile browser or GitHub Codespaces)
1. Create a **new staging** Cloudflare D1 database: \`ivy-mobile-intake-staging\`.
2. In \`cloud-mobile/\`, copy \`wrangler.example.jsonc\` to \`wrangler.jsonc\` (ignored if configured).
3. Replace D1 database_id with the newly created staging DB ID.
4. Configure Cloudflare Access app policy for only OWNER email and protect **the whole Worker** (including assets), not just API paths.
5. Set \`TEAM_DOMAIN\` (your \`https://team.cloudflareaccess.com\` URL), \`ACCESS_AUD\` (Access application AUD), and \`OWNER_EMAIL\`; these must match exactly.
6. Run \`npm run check && npm test\`.
7. Run \`npx wrangler d1 migrations apply ivy-mobile-intake-staging --remote --config wrangler.jsonc\` after reviewing the SQL. This is staging only.
8. Deploy to **a new staging Worker name**, never overwrite Ivy or AI Company production: \`npx wrangler deploy --config wrangler.jsonc\`.
9. Confirm Access denies unsigned/API requests; log in as OWNER; verify status, save, duplicate retry, history and stop on smartphone.
10. Initial D1 state is \`paused=1\` (fail closed). To enable intake **after testing Access**, deliberately update the staging control row to \`paused=0\`. Do not enable inference; none is implemented.

Never commit a real owner email, audience, tokens, secrets, raw runtime database, or private prompts. No Cloudflare tokens are needed inside app source; use platform-protected deployment credentials. Respect Cloudflare/GitHub free-tier limits.

## Design boundary
This module is separate because the existing Python service is a full, stateful local build engine. Exposing it over the public internet or forwarding bearer tokens from a browser would be unsafe. A future hosted worker will require a separate authenticated command queue, persistent isolated build storage, job budgets, approval gates, and audit logs before it can safely perform real generation.
