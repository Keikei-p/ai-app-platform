# Status — v0.8.0

## Verified in this build

- Python source compilation: PASS
- Security Self-Check: PASS
- Unit/security/regression suite: 106 tests PASS
- Persistence acceptance: PASS
- LAN Remote acceptance: PASS
- Chat GUI acceptance: PASS
- SNS automation acceptance: PASS
- Production smoke test: PASS
- Generated Windows EXE acceptance: PASS
- Generated Android/iOS Expo typecheck + bundle acceptance: PASS
- Generated Android native debug APK acceptance: verified by the dedicated acceptance workflow; the final v0.8 PR re-runs this check before main merge.

## v0.8.0 — simpler workspace UX

The desktop product remains conversation-first, but the surrounding workspace is now organized around the actions a non-technical user actually needs.

The default landing question is now 「何を作りたいですか？」 and the permanent sidebar is reduced to:
- new chat
- recent conversations
- created apps
- downloads
- recent projects
- settings

Secondary controls such as diagnostics, AI connection and learning mode live under settings instead of competing with the main workflow.

## Persistent conversations

Standalone chats now persist in the local database instead of existing only in process memory.

The conversation library supports:
- automatic first-message titles
- search across titles/project links/message content
- rename
- pin/unpin
- last-updated ordering
- resume after restart
- hiding a conversation from recent history
- linking a conversation to the project created from it

When a conversation later becomes an app project, the earlier discussion is carried into the project conversation instead of being lost.

## App library and detail view

Created projects are surfaced with:
- app name/type
- target platforms
- current status
- quality-gate state
- last update time
- Code Vault version count
- real artifact count

The app detail view combines:
- current spec/usage context
- preview action
- conversation action
- tests
- security report
- build/release readiness
- unresolved capability gaps
- audit history
- Code Vault versions
- safe restore entry point
- real downloadable artifacts

## Honest download center

The download center distinguishes:
- ダウンロード可能 — an artifact file actually exists
- 準備中 — the target was requested but signing/build requirements remain

Only real .zip/.exe/.apk/.aab/.ipa files under a generated project's artifact directory can be exported.

Pending formats do not open a save dialog. Instead they explain the missing step, such as Windows packaging, Android build/signing or Apple signing/iOS build requirements.

## Post-build next actions

After a successful generated-app quality gate, the UI now surfaces the immediate next choices:
- preview
- request a correction
- download

This action bar automatically collapses before the composer on narrow windows so chat input remains the highest-priority control.

## v0.8 generated-app design system

Generated Web apps now use a refreshed design system with:
- calmer spacing and information hierarchy
- improved typography
- consistent cards/forms/buttons
- 48px-class touch targets
- responsive mobile layouts
- overflow protection
- visible focus states
- loading/busy button states
- success/error toast feedback
- confirmation dialogs
- light/dark/system display modes
- purpose-aware themes

Supported design directions include modern, minimal, premium, friendly, business, soft, finance, youthful, future and dark.

Design intent can be inferred from explicit visual language, while domain context can help choose a sensible generated theme without skipping the conversation's design-confirmation step.

SNS automation uses the same v0.8 design foundation and now displays posting states as readable badges such as 承認待ち / 予約中 / 投稿中 / 投稿済み / 再試行待ち / 失敗 / 取消.

## Design AI v0.8

The deterministic quality gate now checks:
- responsive viewport/layout
- touch target sizing
- focus visibility
- content width
- spacing/design tokens
- mobile overflow protection
- readable typography
- semantic structure
- labels/ARIA
- empty state
- information hierarchy
- success/error feedback
- confirmation UI
- light/dark/system readiness
- visual hierarchy

The pass threshold is 90.

A visual-review contract is also written for mobile/tablet/desktop screenshot review so screenshot/visual-diff execution can be added later without redesigning the report schema. Actual screenshot-based AI critique is not yet enabled.

## Existing v0.7 generation guarantees retained

- explicit approval before first build
- bounded optional LLM coding brain
- deterministic fallback
- maximum two automatic repair/retest attempts
- generated-artifact security scan
- secret/path/shell/npm supply-chain checks
- preview blocked on failed quality gates
- Web ZIP + SHA-256 packaging
- Windows EXE packaging path
- Android/iOS generated source validation
- Android debug APK acceptance
- SNS queue/scheduler/manual approval/auto mode/DRY RUN/retry/idempotency/provider adapters
- production/store actions remain approval-gated

## Current limitations before Ver1.0

- The desktop shell is still Tkinter. v0.8 significantly improves information architecture, but a fully web-rendered desktop shell would allow richer animation, card layout and visual polish.
- Screenshot capture and visual-diff Design AI execution are not enabled yet; only the contract and deterministic visual/usability checks are implemented.
- Real SNS posting still requires the operator's provider apps, permissions and credentials.
- Instagram Reels/carousel and X media upload need dedicated provider adapters.
- YouTube interactive OAuth/token refresh is not yet automated.
- iOS production IPA signing/App Store submission and Android production AAB signing/store submission still require external credentials/tooling and explicit approval.
- Legal/safety/provider checks remain guardrails, not guarantees.
