# AI App Platform v0.8.0

AI App Platform is a local-first, conversation-first app-building environment. Describe what you want, review the brief, explicitly approve the build, then let the platform generate, test, security-check and package the result.

## v0.8.0 — from chat to something you can actually use

The main workspace is now organized around a simple lifecycle:

**話す → 作る → 確認する → 修正する → 履歴を見る → ダウンロードする → 使う**

### Cleaner AI-first desktop UX

The landing screen asks 「何を作りたいですか？」.

The sidebar is intentionally small:
- 新しいチャット
- 最近の会話
- 作成したアプリ
- ダウンロード
- 最近のプロジェクト
- 設定

Advanced tools stay out of the main path until needed.

### Persistent chat history

Chats are stored locally and can be searched, renamed, pinned and reopened after restart. A chat can later become an app project without losing the earlier discussion.

### Created-app library

Each app exposes its status, targets, quality state, spec, tests, security review, build readiness, history, Code Vault versions, preview and artifacts in one place.

### Honest downloads

The download center never treats a missing file as downloadable.

Real generated ZIP/EXE/APK/AAB/IPA artifacts are marked ダウンロード可能. Requested formats that are not built yet are marked 準備中 and explain the next required step.

### Better generated-app design

Generated Web apps now include:
- responsive mobile-first layout
- modern spacing and typography
- consistent cards/forms/buttons
- touch-friendly controls
- success/error toast feedback
- confirmation dialogs
- light/dark/system display modes
- purpose-aware design themes
- stronger Design AI checks

The design themes include modern, minimal, premium, friendly, business, soft, finance, youthful, future and dark. Domain context helps choose a sensible look, but explicit visual preferences still take priority.

### SNS automation UI

Generated SNS automation apps keep the v0.7 queue/scheduler/provider architecture while adopting the v0.8 design system. Posting states are easier to scan and the page retains the safe DRY RUN/manual-approval defaults.

### Build and quality pipeline retained

v0.8 keeps the v0.7 safety guarantees:
- explicit build approval
- bounded optional LLM code edits
- deterministic fallback
- max-two repair/retest loop
- artifact security scan
- preview gate
- Web ZIP + SHA-256
- Windows EXE packaging
- Android/iOS source validation and bundling
- Android debug APK acceptance
- production/store actions require explicit approval

## Validation

Current v0.8 integration evidence includes:
- 106 unit/security/regression tests PASS
- Security Self-Check PASS
- Chat GUI acceptance PASS
- SNS automation acceptance PASS
- Windows generated EXE acceptance PASS
- Android/iOS generated source acceptance PASS

The release PR also runs the dedicated Android native APK acceptance before main is updated.

## Aivy Guardians and Candidate Arena

Aivy now runs additional deterministic guardians around normal builds:

- Regression Guardian blocks completion when a previously passing critical gate regresses.
- Requirement Guardian stores requirement-to-evidence coverage without pretending semantic proof.
- Dependency Guardian checks offline dependency hygiene and explicitly distinguishes that from live CVE intelligence.
- Accessibility Guardian performs deterministic static HTML checks and can block high-severity accessibility failures.
- Performance Guardian tracks static source budgets without inventing runtime latency.
- Project Memory stores certified, project-local development history.
- Candidate Arena compares already-evaluated candidates and never auto-applies a winner.
- Model Benchmark records measured provider/model outcomes from verified builds.
- Aivy Health summarizes projects, specialists, missions, learning, and model observations.

The Web project inspector surfaces Guardian state, and Settings shows Aivy Health and Model Benchmark summaries.

## Parallel Sandbox Workers

Aivy can now run Research, Architecture, Coding, Test, Design and Security specialists in parallel over separate project snapshots. Workers cannot write the live source project; secret-style files and runtime/internal directories are excluded from their snapshots. The live project is fingerprinted before and after the parallel review, and a mismatch blocks the result.

Mission Control uses this parallel review before the reviewed execution council and before build approval. Actual source changes remain single-writer operations in the existing safe build pipeline.

## Mission Control


Aivy now includes a persistent Mission Control foundation for long-horizon work. Missions preserve their goal, project, plan, phase, approval state, evidence references and history across restarts.

Mission execution starts with reviewed preflight and specialist checks. Code generation still stops at an explicit approval boundary, and approved builds continue through the existing test, security, recovery, certificate and learning pipeline.

This is durable local orchestration, not unlimited background computing: a powered-off PC cannot continue local work, and an interrupted in-memory build must resume from a safe reinspection boundary.

## Aivy Learning Flywheel


Verified successful builds now feed a dedicated Learning Flywheel. Aivy records only evidence-backed outcomes that pass Tests, Security, Design and Preview learning gates, together with the Development Certificate/Postflight evidence, the model route used, repair count and safe source-file hashes.

The verified lesson is also written into Development Memory for relevant reuse on future builds. A supervision-candidate view is prepared for a future Aivy-specific model, but automatic fine-tuning remains disabled until dataset review and benchmark gates are added.

The Web settings screen shows the current number of verified learning examples and their average score.

## Important boundaries

Generated projects, runtime databases, logs, API keys, OAuth tokens, signing keys and user data are not committed to Git.

Live SNS publishing, production signing and store publication require the user's own external accounts/credentials and remain approval-gated.

Screenshot-based visual-diff critique is prepared at the report-schema level but is not yet executing screenshots automatically.

## One-click browser setup

For a Windows PC that still has an older Aivy copy, download just `OPEN_AIVY_WEB.bat` from the `develop` branch and double-click it.

It installs the current development copy into `%USERPROFILE%\Aivy-Latest` without modifying the old Aivy folder, safely fast-forwards future updates, and then opens Aivy Web. If local source edits are found, it refuses to overwrite them.

## Browser-first development

Until the desktop product is considered complete, the recommended development and verification surface is Aivy Web.

For normal daily use on Windows, double-click `AIVY_WEB_SILENT.vbs`. It launches the same safe updater and Web server with the console window hidden, so the browser opens without leaving a black terminal window on screen. If the latest Aivy installation is not found, it shows a clear message instead of silently failing.


On Windows, double-click `AIVY_WEB.bat`. It uses the same safe `develop` auto-update path, runs preflight, starts the loopback-only Platform API, and opens Aivy in the default browser at `127.0.0.1:8766`.

The browser UI uses the real local Platform Service rather than a mock screen, so conversations, projects, agent planning, knowledge, build state and downloads can be exercised through the same Core. Closing the accompanying Aivy Web console stops the local server.

This does not publish Aivy to the public internet. It is a local browser development surface; production hosting remains a separate later step.

## Open the latest Aivy

On Windows, use `AIVY_WEB.bat` during development or `AIVY.bat` for the desktop shell.

By default it follows `develop`, the active Aivy integration branch. Before every launch it checks GitHub and only applies a fast-forward update. If local code changes are present, automatic updating is skipped instead of overwriting them. Update failures also fall back to the current local copy; the launcher never uses `git reset --hard`.

Use `AIVY.bat stable` when you intentionally want the tested `main` branch.

For first-time setup or to repair an existing Git installation, run `INSTALL_OR_UPDATE.bat`. It follows the same safe-update rules and keeps runtime user data outside Git.

## Run

Windows: `START.bat`

Validation: `CHECK.bat`

## Git workflow

- `main`: stable and tested
- `develop`: active integration
- `feature/*`: larger isolated changes

GitHub remains the source of truth for platform code.
