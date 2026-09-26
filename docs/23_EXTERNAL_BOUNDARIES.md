# 23 自作範囲と外部境界

## 自作する中核
AI orchestration, requirements, Safety Gate, project/code history, tests, maintenance, improvement loop, remote protocol/control, worker routing, cloud adapters, billing entitlement logic, UI, audit, backup/rollback, localization, release workflow.

## 接続する外部権限
- Apple signing/App Store review
- Google Play developer/review/billing requirements when Play is used
- Microsoft Store review when Store is used
- payment networks/processors
- customer-selected cloud providers
- internet/physical compute resources

The product must minimize lock-in by keeping these behind adapters. It must never claim external review, legal compliance, uptime, or payment-network approval is guaranteed.
