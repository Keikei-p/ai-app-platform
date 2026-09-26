# Current limits - v0.4.8

- AI Core is still an application-development orchestration skeleton, not a ChatGPT-class general model.
- Generated login UI is not yet a complete production authentication backend unless a real auth adapter is connected.
- LAN Remote Beta is enabled only after local user action. It is not an internet remote-access solution.
- LAN Remote Beta uses HTTP inside the trusted LAN; do not use it on public/untrusted Wi-Fi and never port-forward it to the internet.
- Remote Windows build is not exposed yet; v0.4.8 remote actions are safe task-level operations only.
- Hosted Worker, production billing, app-store submission, and production cloud deployment are not enabled.
- Code Vault stores full project-source snapshots and may consume more disk space as history grows.
- Local update packages are integrity-checked, but automatic HTTPS update download remains disabled until publisher-signature verification is implemented.
- PyInstaller EXE self-update is not enabled yet; use source/START.bat mode for in-app update testing.
- Legal/Safety checks are guardrails, not legal guarantees.
