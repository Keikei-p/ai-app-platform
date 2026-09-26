# AI App Platform v0.5.2

AI App Platform is a local-first app-building partner. The main experience is now conversation-first: describe the app, answer only the missing questions, let the platform generate/test it, then continue the same chat to request corrections.

## v0.5.2 milestone

- ChatGPT-style conversation-first desktop UI: neutral sidebar, spacious chat, clear composer, and secondary controls kept out of the main flow.
- Live build progress: requirement review → design → generation → design review → automated tests → completion is visible while work runs in the background.
- Instant new chat: opening a new chat no longer forces a project-name dialog; the first message creates and names the project automatically.
- Clearer actions: labels such as "アプリを確認", "テスト結果", "履歴・復元", and "設定・診断" describe exactly what each control does.
- Reliable composer controls: Enter sends, Shift+Enter creates a new line, and the send button shows busy/error state clearly.
- Chat-first project creation: a first message can create the project automatically.
- Requirement collection: target platform and design direction are asked only when missing.
- Human-correction learning: corrections are stored in Development Memory and can influence later work.
- Design AI gate: generated Web UI is checked for responsive layout, touch targets, focus visibility, spacing/design tokens, and accessibility basics.
- Functional Web generation: optional authentication + SQLite persistence + session/CSRF-protected API, not only a visual mock.
- Mobile source generation: one Expo/React Native project can target Android and iPhone/iPad.
- Capability/GAP reporting: missing APK/AAB/IPA, signing, payment-provider decisions, or other external steps are reported with reason/evidence/next step instead of being called complete.
- Learning mode: generated files and architecture can be explained as study material.
- Existing Safety Gate, Code Vault, update engine, backup, LAN Remote Beta, audit and rollback foundations remain.

## One-app principle

Normal users should not need to open PowerShell, unzip source files, edit code, or switch between many browser tabs. The platform keeps chat, project state, quality status, preview, history and update controls in one desktop application. Advanced details remain available when needed.

## Current mobile status

v0.5.0 generates Android/iOS Expo/React Native source and validates the project structure. It does **not** claim APK/AAB/IPA or store submission is complete until signing/build/store requirements are actually satisfied.

## Run

Windows: `START.bat`

Validation: `CHECK.bat`

## Git workflow

This repository is the source of truth for AI App Platform program code.

- `main`: stable and tested
- `develop`: active integration
- `feature/*`: larger isolated changes

Runtime user data, generated projects, logs, backups, credentials, API keys, certificates and signing keys are not stored in Git. Normal development does not create a new ZIP or `.aipupdate` file for every change. Release artifacts are produced only from verified version tags.
