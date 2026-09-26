# Security & Code Review — through v0.4.8

Review date: 2026-09-25

## Verdict

**Approved for local development MVP testing only.**

This build is intentionally *not* approved yet for public internet remote access, commercial production hosting, live billing, production database mutation, or unattended store submission. Those capabilities remain disabled/unimplemented until their dedicated security gates are completed and independently reviewed.

## Verification performed

- Python source compilation: PASS
- Unit/security tests: 25/25 PASS
- End-to-end smoke test: PASS
- Preflight/readiness checks: PASS in the review container
- Security self-check: PASS
- ZIP integrity: checked before final packaging
- Manual source review of safety, permissions, remote command gate, worker executor, database, backup/restore, generated HTML escaping, project paths, build scripts
- Static pattern scan: no runtime `eval`, `exec`, `os.system`, `shell=True`, generic `Popen`, unsafe pickle load, or inbound network-listener dependency
- Runtime dependency surface: Python standard library only; PyInstaller is build-time only

## Security properties present

### AI / policy separation
- SafetyGate runs before generation.
- PermissionEngine sits outside the model/generator.
- Certain constitution actions are always blocked: disabling safety, self-elevation, erasing audit logs, erasing all backups.
- Production/destructive action names require human approval in the policy layer.

### Remote-control foundation
- There is **no public network listener** in this build.
- Remote command signatures use HMAC-SHA256.
- Remote secret must be at least 32 bytes.
- Commands have short maximum TTL and clock-skew checks.
- Command size is bounded.
- Project slug is validated before filesystem access.
- Accepted command IDs are persisted in SQLite, so duplicate/replay IDs remain blocked after restart.
- Only allowlisted actions are accepted remotely.
- A client-supplied `approved=true` style flag cannot enable a non-allowlisted remote action.
- WorkerExecutor exposes no generic shell/exec action.

### Filesystem / backup
- Project slugs are sanitized and bounded.
- Worker paths must resolve under the workspace root.
- Backups skip symlinks.
- Restore rejects absolute/parent-traversal archive entries and symlink entries before extraction.
- Restore requires explicit confirmation and creates a pre-restore backup first.
- Runtime state (`data/`, `logs/`, `backups/`, `workspace/`) is excluded from Git.

### Data / logging
- SQLite writes use parameterized queries.
- Audit/job/remote detail storage performs best-effort redaction of common passwords/tokens/secrets/private keys.
- Cloud profile files intentionally contain non-secret metadata only in this version.
- No live payment credentials are handled in this version.

### Generated web content
- User-supplied project name/summary are HTML-escaped before insertion.
- A unit test verifies common script/image injection strings are escaped.
- Current generator is capability-limited; it does not execute arbitrary AI-generated code.

### Build reproducibility
- Local runtime has no third-party package dependency.
- Windows packager is pinned to PyInstaller 6.22.3 in `build_windows.bat` instead of installing an unspecified latest version.

## Issues found during this review and fixed in v0.4.2

1. Remote project slugs could have become a future path-traversal risk once remote networking is enabled.
   - Fixed with strict slug validation and workspace-root containment checks.
2. ZIP restore previously used broad extraction semantics.
   - Replaced with validated member-by-member safe extraction; traversal/symlink entries are rejected.
3. Audit/job/remote details could record obvious secret strings.
   - Added best-effort redaction before persistence.
4. Short HMAC secrets were accepted by the remote signing helpers.
   - Now minimum 32 bytes.
5. A future caller could have passed an `approved` boolean to the remote gate.
   - Non-allowlisted remote actions are now rejected regardless of a client-side approved flag.
6. Git ignore rules did not exclude all runtime logs/backups.
   - `data/*`, `logs/*`, `backups/*`, and `workspace/*` are now excluded.
7. PyInstaller installation was unpinned.
   - Windows build script now pins 6.22.3.

## Known limits before public/commercial use

- SafetyGate is currently deterministic/keyword-based. It is not sufficient alone for a public general-purpose app generator.
- No authenticated internet remote API, device pairing, MFA, certificate pinning, rate limiting, or recovery flow exists yet.
- ApprovalStore is local scaffolding; it is not yet tied to authenticated user identity/MFA.
- SQLite and local ZIP backups are not encrypted at rest; current protection relies on Windows/device security.
- No OS secure credential vault integration yet.
- No dependency vulnerability scanner, SAST/DAST, sandboxed execution of arbitrary generated code, or container isolation yet.
- Current generated-app tests are structural/basic, not production-grade security tests.
- Windows code signing, Apple signing/notarization, Android signing, and store submission are not implemented yet.
- No independent penetration test or third-party security audit has been performed.

## Gate before enabling remote/public mode

Do not expose a port or public listener until at minimum:
1. device pairing + key rotation/revocation,
2. OS secure secret storage,
3. authenticated user/session model + MFA for privileged approvals,
4. TLS transport and replay/rate-limit protections,
5. process/container sandbox for generated builds,
6. dependency/SAST scanning,
7. encrypted backups and restore drills,
8. independent security review/pentest,
9. production incident/rollback plan,
10. legal/privacy review for intended launch regions.


## v0.4.4 addendum
- Editable GUI fields now have explicit clipboard/edit shortcuts and a right-click edit menu.
- Dev and frozen Windows builds now share a stable per-user state directory.
- Legacy project-local workspaces are copied forward without overwriting existing persistent projects.
- Database startup re-indexes valid `project.json` files so project lists recover if the DB is recreated.
- Post-change verification: 25/25 unit tests PASS, generation smoke test PASS, security self-check PASS, GUI input select/paste/undo/backspace/copy check PASS.


## v0.4.7 update-engine review

- Local packages only; no network updater is enabled.
- Every update package requires a product/version manifest and per-file SHA-256.
- Same/older versions are rejected.
- Archive traversal, symlinks, duplicate members, unexpected payload files and blocked paths are rejected.
- Update writes are restricted to application source/tests/docs and an explicit root-file allowlist.
- Runtime data/workspace/logs/backups/config and build/git directories cannot be targeted by update manifests.
- The selected package is re-hashed/re-validated immediately before apply.
- User data backup and application snapshot are created before apply.
- Automated compile/security/unit/acceptance/smoke checks run before and after update.
- Post-update validation failure triggers application rollback.
- Remote HTTPS updates remain disabled until publisher-signature verification is implemented. SHA-256 is treated as integrity evidence, not publisher authentication.
- Frozen EXE self-update remains disabled until a dedicated helper is implemented.

## v0.4.8 LAN Remote Beta review

- Inbound listener code isolated to `src/core/remote_server.py`.
- No UPnP, NAT-PMP, router port-forwarding, public tunnel, or cloud relay code.
- LAN listener starts only after local user action.
- Pairing uses a 10-character one-time code with five-minute expiry.
- Paired devices receive independent 32-byte HMAC keys.
- Windows stores remote device secrets with DPAPI when available; non-Windows test fallback relies on user-local file permissions.
- Commands use HMAC-SHA256, issue/expiry timestamps, and unique command IDs.
- Accepted command IDs are persisted in SQLite to reject replay.
- Remote worker has no generic shell/exec/PowerShell action.
- Production deploy, destructive DB actions, billing changes, and credential operations are not in the remote allowlist.
- Remote body size is limited and server emits no-store / nosniff / frame-deny security headers.
- Emergency stop disables remote service and supports revoking all paired devices.
- v0.4.8 LAN transport is HTTP and therefore only approved for trusted private LAN testing; it is not approved for public/untrusted Wi-Fi or internet exposure.
- Final remote architecture remains outbound TLS Relay so the home PC does not require a public inbound port.
