# AI App Platform v0.6.3

AI App Platform is a local-first app-building partner. The main experience is now conversation-first: describe the app, answer only the missing questions, let the platform generate/test it, then continue the same chat to request corrections.

## v0.6.3 milestone

- **Category-free landing:** removed the 業務アプリ / 予約アプリ / 相談から shortcut choices. Users start by simply describing what they want.
- **Premium AI-first welcome:** the empty-chat screen now uses a focused visual identity, a central AI mark and the message 「つくりたいものを、話すだけ。」 instead of template-choice UI.
- **Cleaner information hierarchy:** project-only actions such as preview and test details stay hidden until a project actually exists.
- **Contextual progress UI:** the large progress card is hidden while idle and appears only when work is happening; compact windows still retain a small AI status indicator.
- **Refined visual system:** updated neutral surfaces, typography hierarchy, brand mark, spacing and narrow-window message margins while preserving the pinned composer from v0.6.2.
- **No hidden shortcut regression:** GUI acceptance explicitly rejects the old category choices and verifies the AI-first headline and contextual action visibility.

- **Pinned composer layout:** chat history is now the only vertically flexible row; the composer is structurally pinned to the bottom instead of being pushed out by history content.
- **Pinned send action:** the text area and send button use a two-column layout so long/wide text widgets cannot push the send button outside the visible window.
- **Verified minimum-size visibility:** GUI acceptance now checks that chat history, input field and send button are physically viewable and inside the client area at 820×520, 700×460 and 680×440.
- **Compact-first prioritization:** starter cards, progress chrome, subtitles and helper text collapse before the actual conversation/input area.
- **Compact AI status:** when the full progress card is hidden, a small status indicator remains visible so users can still tell what the AI is doing.
- **Adaptive message margins:** chat bubbles use tighter margins on narrow windows instead of wasting horizontal space.

- **Real AI chat providers:** optional OpenAI Responses API or Gemini API connections provide actual LLM conversation for chat/consultation instead of pretending rule-based replies are equivalent.
- **Explicit AI connection state:** the UI clearly shows AI未接続 until a provider and API key are configured.
- **Secure Windows key storage:** when remembered on Windows, API keys are stored with Windows DPAPI instead of plaintext settings.
- **High-contrast composer:** the chat input no longer uses an overlaid placeholder that can cover typed text; the field uses a white surface, dark text, visible caret and selection contrast.
- **Responsive desktop layout:** at compact widths/heights the sidebar, progress card and secondary controls collapse first while chat history and the composer remain visible.
- **Compact-window navigation:** a menu control restores access to projects/settings when the sidebar is automatically collapsed.
- **Single version source:** the application title now reads the repository VERSION file instead of a stale hardcoded version.
- v0.6.0 approval-first generation remains: casual chat cannot start generation and new builds still require a reviewed brief plus explicit 「この内容で作る」 approval.

- **No accidental generation:** casual chat and vague messages never start app generation.
- **Explicit build gate:** new apps follow 相談 → 要件整理 → 設計確認 → 「この内容で作る」→ generation. Even a message containing「作って」does not bypass this gate.
- **Richer requirement discovery:** the platform confirms who uses the app/how, target platforms, required features, and design direction before showing the brief.
- **Editable design brief:** users can correct the proposed brief in normal chat; generation waits until the revised brief is explicitly approved.
- **Product-style generated Web UI:** internal platform labels and demo metadata are removed from generated apps. Booking, ToDo, inventory, CRM and generic workspaces get purpose-specific information architecture, responsive cards, forms, lists, empty states, and mobile layouts.
- **Approved context reaches generation:** usage flow and design style are stored in AppSpec and passed to the generator rather than discarded after chat.
- **Stricter Design AI:** the quality gate now checks responsive behavior, touch targets, focus states, semantic structure, empty states, information hierarchy, and absence of internal platform branding, with a higher pass threshold.
- ChatGPT-style conversation-first desktop UI, modern Japanese typography, live progress, Code Vault, Safety Gate, backup, updater and Remote foundations remain.

### Important current limitation

v0.6.0 improves requirement discipline and the deterministic generator substantially, but the reasoning/generation engine is still primarily **rule-based**. It is not yet using a full LLM as its coding brain. That means it can now avoid premature/low-context builds and create stronger supported app patterns, but truly bespoke ChatGPT-level architecture and implementation still requires the model-provider layer to be upgraded.

## One-app principle

Normal users should not need to open PowerShell, unzip source files, edit code, or switch between many browser tabs. The platform keeps chat, project state, quality status, preview, history and update controls in one desktop application. Advanced details remain available when needed.

## Current mobile status

v0.6.0 generates Android/iOS Expo/React Native source and validates the project structure. It does **not** claim APK/AAB/IPA or store submission is complete until signing/build/store requirements are actually satisfied.

## Run

Windows: `START.bat`

Validation: `CHECK.bat`

## Git workflow

This repository is the source of truth for AI App Platform program code.

- `main`: stable and tested
- `develop`: active integration
- `feature/*`: larger isolated changes

Runtime user data, generated projects, logs, backups, credentials, API keys, certificates and signing keys are not stored in Git. Normal development does not create a new ZIP or `.aipupdate` file for every change. Release artifacts are produced only from verified version tags.
