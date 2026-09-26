# 13 Remote Security Design

## 原則

- 自宅PCにインターネットから直接ポートを開けない
- LAN Betaは信頼できる同一LANのみ
- 端末ペアリング必須
- 命令はHMAC-SHA256署名 + 有効期限付き
- command_idは一度しか使えない
- Workerはallowlist操作のみ。汎用Shell実行APIを持たせない
- 本番/削除/課金/ドメイン/ストア提出はRemoteから実行させない
- 全操作を監査ログに残す
- 緊急停止・端末失効をローカルPC側に置く

## v0.4.8実装

- 10文字ワンタイムペアリングコード（5分）
- 端末ごと32-byte HMAC鍵
- Windows保存時DPAPI保護（利用可能時）
- HMAC署名
- issued_at / expires_at
- 重複command_id拒否
- RemoteCommandGate
- WorkerExecutor allowlist
- 端末単位失効
- 緊急停止 + 全端末失効
- HTTP body上限
- LAN/local bindだけを持つ標準ライブラリHTTP server
- UPnP / port forwarding / public tunnelを実装しない

## v0.4.8の残課題

LAN HTTPは暗号化されていない。公衆Wi-Fiでは使わない。
最終版は outbound TLS Relay + publisher/endpoint identity + stronger device key architecture へ移行する。
