# Self-made Remote System

## Goal

自宅PCを開発/ビルドWorkerとして家に置き、スマホや別端末から安全に仕事を依頼・監視・承認する。最終的にスマホだけで開発体験を完結させる。

## v0.4.8: LAN Remote Beta

最終Relay導入前の実働段階として、同じ信頼できるWi-Fi/LAN内だけで動くRemote Workerを実装した。

- PC画面から明示的にLAN Remoteを開始
- 10文字・1回限り・5分期限のペアリングコード
- 端末ごとのHMAC鍵
- HMAC-SHA256署名 + expiry + nonce/command_id
- replay拒否
- allowlist Worker
- 端末失効 / 全端末失効 / 緊急停止
- スマホWebコントローラー

LAN BetaはHTTPのため、信頼できるLAN専用。ポート開放やインターネット公開はしない。

## Final architecture

Home PC Agent はインターネットから直接待受せず、自分からRelayへ outbound TLS connection を張る方式を基本にする。

```text
Phone Control App
      ↓ TLS
Command/Relay Service
      ↑ outbound TLS
Home PC Agent
      ↓
Permission Engine → Local Worker
```

## Security controls

- Device pairing
- Short-lived pairing code
- Signed/verified commands
- Expiry + replay protection
- Least privilege allowlist
- High-impact approval
- Audit log
- Emergency stop
- Remote revoke
- Rate/size limits

## Remote phases

### R1 (v0.4.8 started)
LAN status, project create/list, safe AI job, tests, backup, Code Vault.

### R2
Outbound TLS Relay, remote build jobs, job queue/progress, safer smartphone preview.

### R3
Secure file sync and richer remote operations.

### R4
Optional remote screen/control only when needed; task-based control remains primary.
