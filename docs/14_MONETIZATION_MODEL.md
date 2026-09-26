# 14 Monetization Model

料金額は市場検証後に決める。先に構造だけ固定する。

- Free: ローカル中心、お試し
- Personal: 個人向け、Store出力対応
- Pro: プロジェクト上限緩和、高度制作/保守
- Cloud: PCなし向けHosted Worker時間付き
- Business: 複数ユーザー、権限、Hosted Worker増量
- Enterprise: 顧客インフラ/専用Worker/契約対応

課金Coreは決済会社から分離する。
- Web決済adapter
- Apple IAP adapter
- Google Play Billing adapter

従量課金候補:
- Hosted Worker分数
- 保存容量
- 大規模ビルド
- 高負荷AI処理

原則: ユーザー自身のPC/クラウドを使う場合はプラットフォーム原価を抑える。
