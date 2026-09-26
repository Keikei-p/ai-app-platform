# AI App Platform v0.7.0

AI App Platform is a local-first, conversation-first app-building environment. Describe what you want, review the brief, explicitly approve the build, and the platform generates, tests, security-checks and packages the result while keeping risky production actions behind approval gates.

## v0.7.0 highlights

### Real generation quality pipeline

Generated projects now go through design review, automated tests, artifact security scanning, readiness reporting and generated-file SHA-256 manifests. A failed quality gate blocks preview instead of calling the project complete.

When an AI coding provider is connected, it can make bounded multi-file changes inside the generated project. It cannot escape the project directory, overwrite protected platform metadata or write credential/signing files. If AI generation fails, the stable deterministic generator remains available as a fallback.

The platform can also perform up to two bounded automatic repair/retest attempts for code-repairable failures without weakening tests, security checks or approval gates.

### Generated SNS automation apps

Requests for SNS自動投稿 / 予約投稿 / Threads / Instagram / YouTube投稿 / X投稿 can generate a dedicated SNS automation application with:

- scheduled posting queue persisted in SQLite
- manual approval mode by default
- optional auto mode
- DRY RUN by default
- bounded retries and error state
- local idempotency keys
- X text posting adapter
- Threads text create/publish adapter
- Instagram public image URL publishing adapter
- YouTube video upload adapter
- tokens/credentials loaded only from environment variables
- loopback-only server by default
- LAN exposure blocked unless explicit LAN permission and an admin token are configured

The CI acceptance test starts an actually generated SNS server and verifies queue -> approval/auto -> worker -> posted in DRY RUN, so this is not only a UI/template mock.

### Build outputs

- Web: verified distribution ZIP + SHA-256 manifest
- Windows: generated PyInstaller packaging path; generated EXE build and launch self-test verified on Windows CI
- Android/iOS: Expo/React Native source, TypeScript validation and Android/iOS bundling verified
- Android: native debug APK generation verified in CI
- Production Android/iOS signing and store submission remain external credential/approval steps

## Important boundaries

SNS provider credentials, OAuth tokens, signing keys and other secrets are not stored in Git. Live provider publishing is not executed in CI. Provider API permissions, review requirements, rate limits and commercial terms can change, so live deployment must re-check the current official provider requirements.

Production deployment, store submission and other consequential external actions remain explicit-approval operations.

## Run

Windows: `START.bat`

Validation: `CHECK.bat`

## Git workflow

This repository is the source of truth for AI App Platform code.

- `main`: stable and tested
- `develop`: active integration
- `feature/*`: larger isolated changes

Runtime user data, generated projects, logs, backups, credentials, API keys, certificates and signing keys are not stored in Git.
