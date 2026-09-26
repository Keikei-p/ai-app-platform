# Product Requirements

## Primary user groups

1. 初心者・個人: 開発知識なしでアプリを作りたい
2. 個人開発者: 制作・保守を高速化したい
3. 制作会社: 複数顧客の制作/運営を効率化したい
4. 中小企業: 社内アプリ・顧客向けアプリを作りたい
5. 法人: 自社インフラ/BYOCで安全に利用したい
6. PCを持たないユーザー: スマホだけで利用したい

## Core functional requirements

- Natural language app request
- Requirement clarification
- Project creation and version history
- AI-assisted generation and modification
- Automated testing and regression checks
- Safety Gate before execution
- Approval gates before high-impact actions
- Preview and feedback loop
- Platform-specific build/export
- Cloud connection profiles
- Remote worker control
- Monitoring and maintenance
- Rollback
- Internationalization
- Billing/subscription
- Audit log
- Team/role management (later)

## Quality requirements

- Local-first where possible
- Offline-capable basic project management
- Secrets never stored in source code
- Default-deny high-impact operations
- Recovery before autonomy
- Mobile-first control experience
- Explain what the AI changed and why
- Every autonomous change must be attributable and reversible
