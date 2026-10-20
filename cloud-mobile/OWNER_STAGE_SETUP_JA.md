# Ivyスマホ版｜初回だけ必要な安全セットアップ

これは既存の `main` やAI COMPANY OSには触れない、**新規Cloudflareステージング環境**の構築手順です。
**本番公開・有料APIの有効化・PRマージは含みません。** 準備と設定にはCloudflare OWNERアカウントが必要です。

## 作業の前に
- CloudflareのダッシュボードへOWNER自身でログインできる。
- Zero Trust / Accessの利用可否、無料枠・課金設定を確認する。
- GitHubのDraft PR #36 / ブランチ `mobile/hosted-pwa-intake-20261021` を使う。
- OWNERメール、Access AUD、Cloudflare認証情報は **チャット・GitHubコミット・スクショに書かない**。
- 最初の配置に限り、ブラウザ版Codespaces等の安全なCLI実行環境が必要。無料枠・停止後の費用に注意。

## 1回限りの作業（先に接続しない・公開しない）

1. Cloudflareで新規ステージングD1 **`ivy-mobile-intake-staging`** を作成し、そのIDを手元の安全な場所に控える。
2. PR #36のブランチを手元またはCodespacesに開く。 `cloud-mobile/wrangler.example.jsonc` を同じフォルダの **`wrangler.jsonc`** へコピー。これはGit追跡対象外の個人用設定。
3. `database_id`、`TEAM_DOMAIN`、`ACCESS_AUD`、`OWNER_EMAIL` を自分のCloudflare情報で置き換える。 `ENABLE_OWNER_RESUME`、`AI_DESIGN_ENABLED`、`AI_BUDGET_OWNER_APPROVED` は **全てfalseのまま**、AI bindingは追加しない。
4. 重要：`workers_dev: false` のまま配置準備をする。 **スマホ用URLをいきなり有効化しない。**
5. `cloud-mobile` ディレクトリで `npm run check && npm test` を実行する。
6. SQLの影響先が新しいステージングD1だけであることを確認し、 `npx wrangler d1 migrations apply ivy-mobile-intake-staging --remote --config wrangler.jsonc` を実行する。これで `paused=1`、保存・生成は停止状態。
7. `npx wrangler deploy --config wrangler.jsonc` で **URLを無効にした新規ステージングWorker** を配置する（既存サービスのWorker名は使用しない）。
8. Cloudflareの **Workers & Pages → 新規Worker → Access → Protect this Worker behind Access** で、このWorkerの **全ドメインとプレビューを保護**する。OWNERのメールアドレスだけを許可し、「全員」「ドメイン全体を許可」は使わない。保護の範囲は **production and preview** の両方。
9. AccessがWorker全体へ設定されたことを確認したら、個人用 `wrangler.jsonc` の `workers_dev` を `true` にして再度 `npx wrangler deploy --config wrangler.jsonc` する。この後に初めてスマホで利用できるURLが現れる。
10. シークレットモードでアクセスしてAccessログインが必要なことを確認。OWNERでサインインし、`/api/v1/status` が認証後に開けることを確認する。初期状態は停止表示で正常。

## 停止を解除してWebテンプレートをテスト

Access確認が終わったあとに限り、`wrangler.jsonc` の **`ENABLE_OWNER_RESUME` のみ `true`** にしてステージングを更新する。

その後、スマホPWAの安全管理からOWNERが **「受付を再開する」** を選び、次の順番で試す。

1. ToDo依頼 → 固定Webアプリ生成 → プレビューで追加・編集・完了・削除。
2. HTMLダウンロード → 単体で開く → ブラウザ保存とJSONバックアップ。
3. 別のWeb依頼を入力 → 過去の依頼を呼び出して修正依頼。
4. 緊急停止 → 未実行依頼の作成が拒否される → 保存済みの結果は消えない。
5. 別ユーザー/ログイン無しでAPIとHTMLダウンロードが拒否される。
6. Windows PCを完全OFFにし、スマホで同じ操作を再確認する。

### iPhone / Android ホーム画面追加
- iPhone: Safari → 共有 → ホーム画面に追加。
- Android: Chrome → メニュー → インストール（またはホーム画面に追加）。

## 重要な未完成範囲

- ToDo・メモ・紹介ページは **既定の固定テンプレート**。自然言語から自由なWebアプリをAIが書く機能ではない。
- AIによる任意のコード生成・隔離テスト・修復・APK/iOSビルド・本番公開は未接続。
- Cloudflare Workers AIは **有効化しない**。利用料金を確認し、OWNERが改めて承認するまで初期OFF。
- 実機スマホテストとPC-OFFのクラウド動作は、上記の**ステージング操作を実行するまでは未確認**。

Cloudflare公式： https://developers.cloudflare.com/workers/configuration/cloudflare-access/
