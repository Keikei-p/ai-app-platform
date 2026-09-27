# Current limits - v0.8.0

- The desktop shell is still Tkinter. The information architecture and compact behavior are substantially improved, but a web-rendered desktop shell could provide richer transitions and component styling.
- Design AI performs stronger deterministic layout/usability checks and writes a screenshot-review contract, but it does not yet capture/render screenshots or run visual-diff model critique.
- The created-app library currently uses project metadata/status rather than automatically captured preview thumbnails.
- Conversation removal from the recent list is non-destructive for project-linked work; the project and Code Vault remain recoverable.
- Live SNS publishing requires the user's provider registrations, permissions, OAuth/access tokens and any provider-specific review or paid API access.
- X generation currently covers text posts; X media upload needs a dedicated adapter.
- Instagram generation currently covers public image-URL publishing; Reels/video/carousel flows need dedicated adapters and current Meta API verification.
- YouTube upload generation uses an OAuth access token, but interactive OAuth setup and token refresh are not yet automated.
- Android debug APK generation is verified; production signing/AAB/Google Play submission is not fully automated.
- iOS source/bundle generation is verified; production IPA signing/App Store submission requires Apple credentials/tooling.
- LAN Remote remains a trusted-LAN feature, not a public-internet remote-control solution.
- Hosted production deployment adapters and full subscription billing remain incomplete.
- Code Vault full-source history can consume increasing disk space.
- Publisher-signed automatic HTTPS self-update for packaged desktop releases remains future work.
- Legal, safety, dependency and provider checks are guardrails rather than guarantees.
