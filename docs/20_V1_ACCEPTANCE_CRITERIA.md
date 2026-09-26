# 20 Ver1 Acceptance Criteria

Ver1 is complete only when every P0 item passes on a real Windows PC.

## P0 — must pass
- [ ] One-click-ish Windows start (`HOME_QUICK_START.bat`)
- [ ] New project creation
- [ ] Natural-language request produces AppSpec + starter files
- [ ] Safety Gate blocks forbidden request
- [ ] High-risk request stops for review
- [ ] Automatic snapshot before AI changes
- [ ] Local project tests pass/fail correctly
- [ ] Failed test prevents release path
- [ ] Audit/job records are saved
- [ ] Manual backup can be created and validated
- [ ] Diagnostics report can be generated
- [ ] Release-risk checklist generated per app
- [ ] Home-PC remote command gate validates signature/expiry/replay
- [ ] Remote executor cannot run arbitrary shell commands
- [ ] Human approval object is one-time and scoped
- [ ] Web preview opens locally
- [ ] Windows packaging test produces a launchable artifact on the user's PC

## P1 — next after local Ver1
- [ ] Paired smartphone controller
- [ ] Secure Home PC Worker daemon
- [ ] Cloudflare preview deployment adapter
- [ ] Secure secret storage
- [ ] Real local coding model adapter
- [ ] Android build toolchain adapter

## Explicitly not required for Ver1
- App Store/Google Play production submission
- Hosted Worker production fleet
- Full subscription billing
- All-country legal coverage
- General-purpose ChatGPT-class AI
