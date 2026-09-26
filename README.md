# AI App Platform v0.6.0

AI App Platform is a local-first app-building partner. The main experience is now conversation-first: describe the app, answer only the missing questions, let the platform generate/test it, then continue the same chat to request corrections.

## v0.6.0 milestone

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


