AI App Platform v0.5.2

1) START.bat starts the app
2) CHECK.bat runs all checks
3) BUILD_WINDOWS.bat builds the Windows executable
4) DIAGNOSTICS.bat collects diagnostics if something fails

Main v0.5.0 changes:
- Chat-first app creation and correction flow
- Functional Web generation with auth/SQLite/session/CSRF
- Development Memory and Design AI
- Android/iPhone Expo source generation
- Capability/GAP reporting so unfinished work is not called complete
- Existing Safety Gate, Code Vault, backup, update and LAN Remote Beta remain

LAN Remote Beta is for trusted private networks only.
Do NOT port-forward the Remote port to the internet.
User data stays under %LOCALAPPDATA%\AI-App-Platform.

GitHub is the source of truth for program code. Runtime user data and secrets must never be committed.


v0.5.2 usability update:
- Chat-first layout redesigned for clarity
- Live visible work stages while AI builds/tests
- Instant new chat without naming dialog
- Clearer action names and simplified advanced controls
- Background generation keeps the interface responsive


v0.6.1 chat update:
- High-contrast visible message composer
- Responsive compact-window layout that keeps chat visible
- Optional OpenAI / Gemini real LLM conversation
- Explicit AI未接続 state until a provider key is configured
- Approval-first generation from v0.6.0 remains enforced


v0.6.2 responsive fix:
- Chat composer is pinned to the bottom
- Send button stays visible at compact sizes
- Chat/history/input visibility is acceptance-tested at 680x440
- Nonessential UI collapses before the conversation area
