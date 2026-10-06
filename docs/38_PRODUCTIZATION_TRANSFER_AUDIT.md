# Ivy Productization / Transfer Audit

Date: 2026-10-06
Branch: develop
Scope: external services, credentials, owner-specific dependencies, transfer/OEM readiness.

## Summary

| Area | Classification | Current finding | Required change |
| --- | --- | --- | --- |
| OpenAI / Gemini credentials | 改善必要 | Windows DPAPI encrypted values may coexist inside settings.json. Environment variables are also supported. | Move persistent secrets into a dedicated Credential Store and keep only provider/model metadata in settings. |
| Ollama | 安全 | Local fallback uses localhost by default and requires no account secret. | Promote to a first-class Connector and expose status/test UI. |
| GitHub | 危険 | Development launchers contain the developer repository URL. GitHub is also treated as platform source-of-truth rather than a buyer-owned connector. | Remove developer-specific repository dependency from transferable product paths; add buyer-owned GitHub Connector. |
| Firebase | 未確認 / 未接続 | Cloud profile metadata supports Firebase but no unified authenticated Connector exists. | Add Connector schema/status and keep project/account configuration owner-controlled. |
| Cloudflare | 未確認 / 未接続 | Cloud profile metadata supports Cloudflare but no unified authenticated Connector exists. | Add Connector with buyer-owned token/config and safe connection test. |
| Google / Play | 未確認 / 未接続 | Gemini exists; Google Play credentials are not a unified Connector. | Separate Gemini from Play distribution credentials. |
| Apple Developer | 未確認 / 未接続 | Signed IPA remains intentionally unsupported without external owner credentials. | Add optional distribution Connector metadata; never bundle signing material. |
| .env / key files | 安全 | .gitignore excludes .env, private keys, signing material and credential/secret JSON. | Keep the rule and add transfer audit enforcement. |
| Logs / chat secret leakage | 改善必要 | Redaction exists, but credential setup is not structurally separated from all normal app flows. | Route credential entry only through Connector APIs, redact Connector errors, and scan logs/chat during transfer audit. |
| Ownership / OEM | 改善必要 | Aivy identity is hard-coded in the product identity module and Web UI. | Add owner/brand profile overlays so product name, organization, support and colors can be changed without core logic edits. |
| Git history secret scan | 未確認 | Runtime SecretsGuard scans settings/projects, not full Git history. | Add transfer audit that scans Git history for secret patterns without returning values. |
| Export / import | 未実装 | No product-level credential-free configuration package. | Add ivy-config.json export/import that excludes secrets. |
| Transfer package | 未実装 | No non-destructive owner-clean transfer package builder. | Add audit -> backup -> explicit package generation flow. |

## Confirmed safety controls

- Runtime data, logs, backups, workspaces and local DB files are excluded from Git.
- .env, private keys, signing keys and credentials/secrets JSON are excluded from Git.
- CloudProfileStore declares and stores non-secret metadata only.
- SecretsGuard reports secret field/path names without returning secret values.
- Redaction removes common API key/token/password/Bearer/JWT/private-key patterns from loggable text.
- Consequential publishing, billing and signing remain approval-gated.

## Productization rule

A transferable Ivy build must not require the original developer's:
- API keys or OAuth tokens
- GitHub account
- Firebase / Cloudflare / Google / Apple accounts
- machine-specific user path
- private runtime workspace
- credential-bearing logs or chat history

Buyer flow:
Install -> Setup Wizard -> choose/connect buyer services -> connection tests -> start Ivy.

Transfer flow:
Audit -> review findings -> backup -> explicit build of credential-free transfer package -> new owner setup.
