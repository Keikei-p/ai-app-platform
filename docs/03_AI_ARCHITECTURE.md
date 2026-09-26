# AI Architecture

## Principle

自作AIは「基盤モデルそのもの」だけを意味しない。アプリ制作に特化した Orchestrator、memory、tool system、evaluation loop、安全層、改善履歴を合わせて独自AIとする。

## Agents

### Orchestrator
依頼理解、タスク分解、エージェント選択、進行管理、失敗時再計画。

### Requirement Agent
曖昧な依頼を機能、データ、権限、対象端末、公開方法に構造化。

### Creation Agent
UI、DB、API、認証、コード、設定を作成・修正。

### Test Agent
unit/integration/UI/build/regression/security smoke tests。

### Maintenance Agent
ログ、クラッシュ、パフォーマンス、失敗ジョブを調査。修正候補を作り、安全な範囲で再テスト。

### Improvement Agent
UX、速度、コスト、保守性、アクセシビリティ改善を提案。

### Compliance Assistant
地域・ストア・データ利用についてチェック項目を提示。法的保証はしない。

## Memory layers

- Product memory: 何を作るアプリか
- Architecture memory: 技術/構成
- Decision log: なぜ決めたか
- Failure memory: 過去の失敗と回避策
- Release memory: 何をいつ公開したか
- User-approved constraints: 変更禁止事項

## Model adapter

Safety/Permissionsとは独立させ、将来ローカルモデル、専用モデル、外部モデル等を交換できる。
