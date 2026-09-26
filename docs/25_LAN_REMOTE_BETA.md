# 25 LAN Remote Beta (v0.4.8)

## 目的

同じ信頼できるWi-Fi/LANにいるスマホから、自宅Windows PCのAI App Platformへ安全な定型作業を依頼する最初の実働版です。

## v0.4.8でできること

- PCの状態確認
- プロジェクト一覧
- 新規プロジェクト作成
- 制作AIパイプライン実行（Safety Gate → 制作 → テスト）
- プロジェクトテスト
- Code Vault保存
- 全体バックアップ
- 保守スキャン等のallowlist操作（内部Worker）

## ペアリング

1. PC版の「リモート」を開く
2. 「同じWi-Fi向けに開始」
3. PCに表示されたURLをスマホで開く
4. PCで「新しいペアリングコード」を発行
5. 10文字コードをスマホへ入力

ペアリングコードは1回限り、5分で失効します。

## セキュリティ

- 任意Shell / PowerShell / 任意実行ファイルの実行APIなし
- 本番公開、DB削除、課金変更、資格情報操作をRemote allowlistに含めない
- 端末ごとに32バイトHMAC鍵を発行
- Windows側の端末鍵はDPAPIで保護（利用可能時）
- 各命令はHMAC-SHA256署名 + issued_at/expires_at + command_id
- command_idはSQLiteで一度しか受理しない（リプレイ防止）
- 端末単位で失効可能
- 緊急停止でRemote停止 + 全端末失効
- 全Remote命令を監査ログへ記録
- HTTP bodyサイズ制限
- PC側処理は一度に1つずつ実行し競合を抑える

## 重要な制限

v0.4.8はLAN Remote Betaです。通信はLAN内HTTPで、TLSはまだありません。

**信頼できる自宅/社内Wi-Fiだけで使用し、ルーターでポート開放しないでください。**
公衆Wi-Fi、ホテルWi-Fi、インターネットから直接到達可能なネットワークでは使わないでください。

最終版は、PCからRelayへoutbound TLSで接続する方式を予定し、自宅PCに外部公開ポートを作らない設計へ移行します。

## Windows Firewall

LAN Remote開始時にWindows Firewall確認が出た場合は、使うなら「プライベート ネットワーク」のみ許可し、パブリックネットワークは許可しない運用を推奨します。
