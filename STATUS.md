# Status — v0.6.0

## Verified targets for this build

- New-project generation requires explicit approval after a visible design brief.
- Casual conversation must not create or generate a project.
- Requirement discovery covers usage context, target platform, feature requirements and design direction.
- Approved usage/design context is preserved in AppSpec and generation.
- Generated Web UI uses product-style purpose-specific layouts instead of internal platform/demo metadata.
- Design AI uses a stricter quality threshold and checks empty states, hierarchy and internal-brand leakage.
- Existing authentication/session/CSRF/SQLite CRUD/user-isolation tests remain part of regression coverage.
- Existing Safety Gate, Code Vault, persistence, Remote and smoke checks remain part of CI.

## Meaning of v0.6.0

This is the first **approval-first** generation milestone. The platform should no longer behave like “say something and it immediately spits out a template.” It must gather context, show what it understood, allow corrections, and wait for an explicit build decision.

## Known gaps before Ver1.0

- The coding/reasoning brain is still primarily deterministic/rule-based; a full model-provider implementation is still needed for truly bespoke ChatGPT-level generation.
- The stronger generator currently has dedicated patterns for common app types; unsupported domains can still fall back to a generic workspace pattern.
- Screenshot/visual-diff based design critique is not yet implemented.
- Android APK/AAB and iOS IPA production signing/store submission are not fully automated.
- Payments, push notifications, advanced realtime systems and third-party APIs need dedicated adapters and approval gates.
- Development Memory is inspectable lesson memory, not autonomous model-weight training.
- AI self-improvement remains constrained: no permission self-elevation or uncontrolled self-modification.
