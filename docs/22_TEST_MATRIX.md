# 22 Test Matrix

| Layer | Required test |
|---|---|
| Safety | benign allow / forbidden block / high-risk review |
| Permission | constitution block / human approval required |
| AI pipeline | request → spec → files → risk report → tests |
| Data | SQLite init / project/audit persistence |
| Backup | create / ZIP integrity / safe restore |
| Code Vault | save / history / diff / hash validate / restore / failure rollback |
| Update | version / manifest / hash / allowlist / tamper reject / rollback |
| Remote crypto | HMAC / expiry / replay / wrong key / device revoke |
| Pairing | one-time code / expiry / attempt limit |
| Remote HTTP | pair / signed command / body limit / security headers |
| Remote task flow | project create → AI pipeline → tests → Code Vault |
| Remote GUI | start/status/URL/pair-code/device list/revoke |
| Worker | allowlist only / path traversal reject / no generic shell |
| Billing | project/worker/multi-user/store entitlements |
| Platform | worker OS requirements, especially Apple/macOS |
| Release | tests + risk + backup + approval gates |
| Packaging | Windows executable launches and retains data |
