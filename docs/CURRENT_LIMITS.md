# Current limits - v0.7.0

- The coding brain now supports bounded LLM-driven file changes, but it is not a general autonomous software engineer and still relies on supported generation architecture plus quality gates.
- Live SNS publishing requires the user's own provider app registration, permissions, OAuth/access tokens and any provider-specific review or paid API access.
- SNS CI uses DRY RUN/mocked provider calls; real production accounts and secrets are intentionally not stored or exercised in repository CI.
- X generation currently covers text posts; X media upload needs a dedicated media adapter.
- Instagram generation currently covers public image-URL publishing; Reels/video/carousel flows need dedicated adapters and current Meta API verification.
- YouTube upload generation uses an OAuth access token, but interactive OAuth setup and token refresh are not yet automated in the generated app.
- Provider APIs can change independently of the platform. Meta Graph/Threads versions are configurable and must be checked against official documentation before live deployment.
- Android native debug APK generation is verified. Production signing/AAB/Google Play submission is not yet fully automated.
- iOS source/bundle generation is verified, but production IPA signing and App Store submission require Apple credentials/tooling and are not yet fully automated.
- LAN Remote remains a trusted-LAN feature, not a public-internet remote-control solution.
- Hosted Worker production fleet, full subscription billing and production cloud deployment adapters remain incomplete.
- Code Vault full-source history can consume increasing disk space.
- Publisher-signed automatic HTTPS self-update for packaged desktop releases remains future work.
- Legal, safety, dependency and provider checks are guardrails rather than guarantees.
