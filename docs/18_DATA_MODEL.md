# 18 Data Model — v1 foundation

## Core records

### User / Organization (future hosted/login layer)
- user_id
- organization_id
- role
- locale / timezone / region
- billing_plan
- status

### Project
- project_id / slug
- owner / organization
- name
- app_spec
- requested targets: web/windows/android/ios/macos
- current_release
- safety status
- release status
- worker preference

### Job
- instruction
- actor
- selected worker
- status
- started/finished timestamps
- result / test result / failure reason

### AuditEvent
Append-oriented history for: request, safety decision, generation, tool action, test, approval, deploy, rollback, maintenance, billing/security changes.

### Approval
One-time, scoped approval. Action + project + expiry must match at consumption. Production/destructive actions never reuse old approval.

### Worker
- home / hosted / enterprise
- OS/capabilities
- online state
- trusted device identity
- current workload
- last heartbeat

### CloudProfile
Non-secret metadata only in normal files. Credentials/tokens must be held in OS secure storage or provider OAuth flows when implemented.

### Release
- target platform
- build artifact id/hash
- test/security/compliance checks
- human approval
- release time
- rollback reference

### Billing
Plan/entitlements and usage are platform-owned records; payment credentials remain with the payment provider/store.
