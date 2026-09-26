# Status — v0.7.0

## Verified in this build

- Python source compilation: PASS
- Security Self-Check: PASS
- Unit/security/regression suite: 96 tests PASS
- Persistence acceptance: PASS
- LAN Remote acceptance: PASS
- Chat GUI acceptance: PASS
- SNS automation acceptance: PASS
- Production smoke test: PASS
- Generated Windows EXE acceptance: PASS
- Generated Android/iOS Expo typecheck + bundle acceptance: PASS
- Generated Android native debug APK acceptance: PASS

## v0.7.0 — generated-app quality pipeline

Generation is no longer judged only by whether files were written.

Each generated project now records:
- automated test results
- design review
- generated-file SHA-256 manifest
- generated-artifact security scan
- build/readiness status
- explicit production/store approval state

Generated artifacts are scanned for obvious secret leakage, unsafe dynamic execution, shell=True, symlink/path escapes, risky npm lifecycle scripts, and non-registry package sources. Failed quality gates block preview.

When a connected coding model proposes changes, its writes are bounded to allowed project text files. It cannot overwrite platform metadata, credential files, build artifacts or paths outside the project. Model failure falls back to the deterministic generator rather than failing the entire build.

When code-repairable quality checks fail, the platform can feed bounded failure details back into the coding brain and retry up to two times. Tests/security/approval gates cannot be disabled by the repair loop.

## v0.7.0 — build outputs

- Verified Web apps can produce a distribution ZIP plus SHA-256 manifest.
- Windows targets receive a generated package launcher/build script.
- With PyInstaller available, the platform can automatically build the verified generated Windows EXE.
- GitHub Windows acceptance has built the generated EXE, launched its self-test and verified writable runtime payload extraction.
- Android/iOS Expo source is typechecked and bundled in CI.
- Android native debug APK generation is verified in CI.
- Production Android signing/AAB and iOS IPA/App Store signing remain external credential/toolchain steps and are not represented as complete until actually performed.

## v0.7.0 — SNS automation generation

Natural-language requests such as SNS自動投稿 / 予約投稿 / Threads / Instagram / YouTube投稿 / X投稿 can select the dedicated social_automation app type.

Generated SNS automation apps include:
- persistent SQLite posting queue
- scheduled posting
- approval mode (default)
- explicit auto mode
- DRY RUN by default
- idempotency keys to avoid duplicate local queue rows
- retry with bounded exponential backoff
- posting state/history fields and errors
- X text-post adapter
- Threads text-post create/publish flow
- Instagram public image URL create/publish flow
- YouTube video upload adapter restricted to media/ files
- credentials read only from environment variables
- loopback-only default server binding
- LAN binding blocked unless AI_APP_ALLOW_LAN=1 and SOCIAL_ADMIN_TOKEN are both configured

End-to-end acceptance starts an actually generated SNS server and verifies:
queue -> pending approval -> approve -> dry-run worker -> posted,
and also verifies that auto mode can queue due posts without the manual approval step.

Provider request-contract tests run without sending real posts. X create-post and YouTube upload endpoints were additionally checked against current official API documentation during this milestone. Meta provider API versions remain externally controlled/configurable because those APIs can change independently of this repository.

## Current limitations before Ver1.0

- Real SNS posting still requires the operator's own API applications, permissions, OAuth/access tokens and any provider review/paid access requirements.
- Live third-party API calls are not performed in CI because production account credentials must not be stored in the repository.
- Instagram generated support currently targets public image-URL publishing; richer Reels/carousel workflows need dedicated adapters.
- X generated support currently targets text posts; media upload is a separate future adapter.
- YouTube access-token refresh/interactive OAuth setup is not yet automated inside the generated app.
- The desktop shell is still Tkinter-based.
- Streaming token-by-token chat and screenshot/visual-diff design critique are still future work.
- iOS production signing/IPA/App Store submission and Android production signing/AAB/store submission still require external credentials and approval.
- Legal/safety/provider checks are guardrails, not guarantees.
