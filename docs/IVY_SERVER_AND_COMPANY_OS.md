# Ivy Server + AI COMPANY OS 安全連携設計（Phase 1）

## 完成目標と運用境界

- **Ivy Server（単独稼働）**：ブラウザ UI、チャット、Mission、ビルド、成果物、ログ。
- **AI COMPANY OS（別製品）**：AI 社長・社員の仕事管理・承認。Ivy が停止しても独立して動く。
- **連携インターフェース**：2つのユーザーDBを共有せず、認証した API 経由の小さなメッセージだけ。
- **Cloud Growth**：GitHub ランナーによるソース監査・PR（別のクラウド環境が必要）。
- **実行場所の区別**：自宅の Ivy Server は PC がOFFなら停止する。Cloud Growth と取り違えない。

## 現在実装したフロー

```
Windows PC/browser <--> Ivy Server 127.0.0.1:8766
                             |
                   Ivy Mission Store (独立DB)
                             |
                   OWNERによるビルド承認
                             |
                    生成 -> テスト -> 保存

AI COMPANY OS (独立DB)
     |  設定済みの専用キー / 同じPC内のHTTPのみ
     +--> GET  /api/v1/company/status
     +--> POST /api/v1/company/missions (queued only)
```

**Ivy Server の単独起動**：既存の `AIVY_WEB_SILENT.vbs` がブラウザ版の静かな起動を行う。
Windowsサインイン後の自動起動は既存 `ENABLE_AIVY_AUTOSTART.vbs` を明示的に
実行した場合に限る。Windowsサービス化やタスク登録は勝手にしない。
すでにポートが占有されている場合は、監視スレッドやDB処理の初期化より前に拒否する。

## AI COMPANY 接続の安全ポリシー

**初期状態：OFF**。同じPCの別サービス以外に連携用 API を公開しない。
第三者・OEM利用者は自分の秘密値を設定する。

1. 32文字以上のランダムな値を Windows 環境変数 `AIVY_COMPANY_BRIDGE_TOKEN` に
   設定する（秘密値はGitHub / docs / チャットへ貼り付けない）。
2. Ivy Server をその環境変数があるプロセスで起動する。
3. AI COMPANY OS 側に同じ値を**秘密情報として安全に設定する**。
   AI COMPANY OS 側のクライアント接続は Phase 2 で統合する。
4. localhost から `X-Ivy-Company-Token` ヘッダーでだけ接続。
5. VPN・公開トンネル・Cloudflareの公開ホストからは連携口を直接使わない。
   リモート動作の Ivy Server では拒否する。

`GET /api/v1/company/status`
- `service` / `integration` / `schema_version` / `mission_intake_enabled`
- ビルド数・履歴健全性・自動承認不可情報だけ。CSRF・目標文・鍵・ファイルパスなし。

`POST /api/v1/company/missions`（JSON）
```json
{"goal":"TODOアプリの設計案を作る","project_slug":"existing-project","max_cycles":1}
```
- **既存のIvyプロジェクトのみ**（存在チェック済み）。新規プロジェクトは自動作成しない。
- goal 最大2000字、slug検査、max_cycles 1～8。追加フィールドを拒否。
- 内部で `PlatformService.create_mission()` のみ呼び出し、登録結果を返す。
- **run_mission_cycle() は呼ばない**。approved_build, deploy, payment, shell は拒否。
- 自動リトライ・重複防止キーは Phase 2 で実装予定。初期段階の呼び出し側は
  タイムアウト時に勝手に再送しないこと。
- データベース共有、コード自動公開、サーバーの自動殺害は一切行わない。

## 開発順序

1. **Phase 1 [実装・CI確認中]** Ivy Server 二重起動時の安全停止、最小 API、
   専用キー・localhost検証、単体・HTTP テスト。
2. **Phase 2 [未実装]** AI COMPANY OS側のクライアント・OWNER管理UI、
   リクエストIDによる永続重複防止、問い合わせ・結果取り込み、両サービス再起動テスト。
3. **Phase 3 [未実装]** Windows実機起動・スリープ・24時間耐久、サービス監視、
   監査ログの機密対策。オーナー承認後に任意の自動再起動機能を追加する。
4. **Phase 4 [未実装]** クラウドの独立監査・改善提案と、レビュー付きPR運用、
   販売・譲渡・OEMの別ユーザー新規セットアップ確認。

## 安全・費用

- 追加の有料サービス不要。localhostだけの連携なのでネット公開しない。
- CIはWindowsソフトウェアの静的・疑似HTTP受け入れ検証に過ぎず、
  ユーザーのWindows10実機稼働や24h耐久・Ollama生成の実証ではない。
- `main` は安定版として残す。既存のstate/workspace/secretsをGit管理しない。
