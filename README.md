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

## Important boundaries

Generated projects, runtime databases, logs, API keys, OAuth tokens, signing keys and user data are not committed to Git.

Live SNS publishing, production signing and store publication require the user's own external accounts/credentials and remain approval-gated.

Screenshot-based visual-diff critique is prepared at the report-schema level but is not yet executing screenshots automatically.

## Browser-first development

Until the desktop product is considered complete, the recommended development and verification surface is Aivy Web.

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
