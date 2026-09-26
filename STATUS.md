# Status — v0.6.1

## Verified in this build

- Python source compilation: PASS
- Security Self-Check: PASS
- Unit/security/regression suite: 56 tests PASS
- Persistence acceptance: PASS
- LAN Remote acceptance: PASS
- Chat GUI acceptance: PASS
- Production smoke test: PASS
- Compact layout keeps chat history and the message composer visible at 720×540.
- Composer foreground/background contrast is verified so typed text cannot be visually identical to the input surface.
- OpenAI and Gemini response parsing is regression-tested without external network calls.
- Casual chat remains separated from build approval; new projects cannot generate before the explicit approval gate.
- Existing auth/session/CSRF/SQLite CRUD/user-isolation and Design AI checks remain in regression coverage.

## What v0.6.1 changes

The desktop experience now treats chat as a first-class product surface rather than a form around the generator. The input field is high-contrast, compact-window behavior prioritizes conversation, and a real LLM provider can be connected for natural conversation.

OpenAI/Gemini connectivity is optional. Without a configured API key the product says AI未接続 instead of implying that local deterministic replies are equivalent to a full LLM.

## Known gaps before Ver1.0

- The app-generation coding brain is still primarily deterministic/rule-based. Real LLM chat is now pluggable, but bespoke LLM-driven architecture/code generation is still a separate next milestone.
- The current desktop shell is still Tkinter-based. Responsive behavior is improved, but a full web-rendered desktop shell would allow a closer visual match to ChatGPT/Gemini-grade UI polish.
- Streaming token-by-token chat responses are not yet implemented; provider replies currently arrive as a completed response.
- Screenshot/visual-diff based design critique is not yet implemented.
- Android APK/AAB and iOS IPA production signing/store submission are not fully automated.
- Payments, push notifications, advanced realtime systems and third-party APIs need dedicated adapters and approval gates.
