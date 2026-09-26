# Safety / Legal / Liability Risk Design

## Objective

賠償リスクを「免責文だけ」に依存せず、製品設計そのものから事故確率と影響を下げる。

## Safety layers

1. Request classification
2. Safety Gate
3. High-risk domain review
4. Tool-level permission checks
5. Automated tests
6. Security checks
7. Human approval for high-impact actions
8. Backups and rollback
9. Monitoring and audit trail

## High-risk domains

Examples requiring stronger review:

- medical/health
- financial decisions
- legal decisions
- children/minors
- biometric/sensitive personal data
- surveillance
- critical infrastructure
- high-impact automated eligibility decisions

## Commercial release checklist

Before public paid launch:

- Terms of Service legal review
- Privacy Policy legal review
- Liability limitation language review
- Data processing map
- Incident response procedure
- Security disclosure/contact process
- Vendor/subprocessor inventory
- Store policy review
- Jurisdiction-specific checks for target markets
- Appropriate cyber/technology liability insurance review

AI compliance checks are assistance, not legal guarantees.

## Evidence retention

For disputes/incidents retain appropriate records of:

- user request
- safety result
- AI plan
- code/version changed
- tests performed
- approvals
- deployment/version
- monitoring outcome
- rollback/fix history

Retention duration must later be defined by legal/privacy requirements and data minimization.
