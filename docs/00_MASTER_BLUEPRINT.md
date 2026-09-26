# AI App Platform — Master Blueprint

## 1. Mission

世界中の人が、専門的な開発知識や高性能PCの有無に関係なく、自然言語でアプリを依頼し、制作・確認・公開・保守・改善まで一つのアプリ内で完結できるプラットフォームを作る。

ただし自由度を高く保ちながら、危険・違法・第三者の権利侵害・重大な規約違反につながるアプリ制作は Safety Gate で停止する。

## 2. Product promise

ユーザー体験の最終形は次の一文に集約する。

> 「作りたいアプリを伝える。AIが作る。確認する。公開する。その後もAIが見守り、直し、育てる。」

## 3. End-to-end lifecycle

```text
Idea / Request
    ↓
Requirement Interview
    ↓
Safety Gate
    ↓
Specification
    ↓
Architecture / UI / Data model
    ↓
Implementation
    ↓
Automated Tests
    ↓
Security & Compliance Checks
    ↓
Preview
    ↓
Human Approval
    ↓
Build / Package
    ↓
Deploy / Store Submission Support
    ↓
Monitoring
    ↓
Investigation → Fix → Re-test → Rollback/Release
    ↓
Continuous Improvement
```

## 4. Worker model

### Home PC Worker
PC所有者向け。重いAI・ビルド・テストを本人PCで行う。スマホは操作端末になる。

### Hosted Worker
PCを持たない利用者向け。プラットフォームが計算資源を提供する。有料プラン/従量課金の中心。

### Enterprise Worker
法人管理下のPC・サーバー・クラウドで実行する。監査・権限・データ分離を強化。

## 5. Platform targets

- Windows: EXE / MSIX
- Android: APK / AAB
- Apple: iPhone / iPad / macOS
- Web: Browser / PWA / hosted web application

AI CORE、Safety、Project、Audit、Billing、RemoteはOS非依存。ビルド/署名/提出だけPlatform Adapterへ分離する。

## 6. AI architecture

```text
User
 ↓
AI Orchestrator
 ├ Requirement Agent
 ├ Build/Creation Agent
 ├ Test Agent
 ├ Maintenance Agent
 ├ Improvement Agent
 └ Compliance Assistant
 ↓
Safety Gate (non-AI authority)
 ↓
Permission Engine (non-AI authority)
 ↓
Tools / Workers / Platform Adapters
```

AIモデル自体は交換可能。自作AIの価値は「アプリ制作・運用の専門ワークフロー、記憶、ツール操作、評価、再計画」に置く。

## 7. Trust architecture

AIより上位に固定ルールを置く。

1. Safety Gate
2. Permission Engine
3. Approval Gate
4. Immutable/append-only Audit Trail
5. Backup & Rollback
6. Least privilege
7. Secret isolation
8. Remote emergency stop

## 8. Commercial model

Free / Personal / Pro / Cloud / Business / Enterprise を想定。Home PC Worker利用者はプラットフォーム側計算費を抑え、Hosted Worker利用者は計算量・保存量・ビルド量を課金可能にする。

決済事業者・Apple IAP・Google Play BillingはAdapter化し、プラン状態や利用量管理は自社Coreで統一する。

## 9. International design

言語、地域、通貨、税表示、タイムゾーン、日付形式、ストア公開地域、データ保存地域、地域別コンプライアンス確認をLocale/Region Profileとして管理する。

## 10. Non-goals for early versions

- ChatGPT級の汎用基盤モデルをゼロから学習すること
- AIに無制限の管理者権限を与えること
- 法律/規約への適合をAIだけで保証すること
- 審査結果や外部サービス稼働を保証すること
- v1から全OSを完全自動ビルドすること

## 11. Success definition

最終成功条件は「非エンジニアがスマホだけで安全にアプリを依頼し、完成・修正・公開・保守まで進められる」こと。

## Code Vault (implemented in v0.4.6)

The local project layer now includes a user-facing Code Vault with simple Save / History / View Changes / Restore controls. AI runs save versions before and after successful changes. Restore creates a safety version first, validates saved file hashes, excludes common secrets and generated dependency/build folders, and attempts automatic rollback if restore fails.
