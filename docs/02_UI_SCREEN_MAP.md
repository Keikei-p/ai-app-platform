# UI / Screen Map

## A. First launch

1. Language / region
2. Sign in or Local-only mode
3. Execution mode
   - This PC
   - Remote Home PC
   - Hosted Worker (future)
   - Enterprise Worker (future)
4. Safety & responsibility overview
5. Optional cloud connection

## B. Main navigation

### Home
- Recent projects
- Current jobs
- Alerts requiring approval
- Worker status
- Maintenance health

### Create
- Large prompt: 「何を作りたいですか？」
- Target selection: Web / Windows / Android / Apple
- Advanced options hidden by default

### Project
- Chat / request history
- Live build status
- Preview
- Files (advanced)
- Versions / rollback
- Tests
- Deployments
- Monitoring
- Improvement suggestions

### Remote
- Home PC online/offline
- Start job
- Pause / emergency stop
- Pending approvals
- Device list
- Audit history

### Cloud
- Connection profiles
- Provider setup wizard
- Permission test
- Deployment target
- No secret shown after save

### Maintenance
- Health score (descriptive, not false guarantees)
- Current errors
- Security updates
- Backups
- Rollback points
- Suggested improvements

### Billing
- Current plan
- Usage
- Invoices/receipts
- Plan change
- Worker compute usage

### Settings
- Language / region / currency / timezone
- Security
- Devices
- Notifications
- Data/export/delete

## C. Project creation flow

```text
Create
 ↓
Natural language request
 ↓
AI summarizes requirements
 ↓
User confirms / edits
 ↓
Safety Gate
 ↓
Build plan
 ↓
Create
 ↓
Preview
 ↓
Feedback chat
 ↓
Ready check
 ↓
Build target
 ↓
Human approval
 ↓
Release
```

## D. Mobile control design

Mobile does not need a full code editor by default. Primary actions:

- Ask AI
- Preview
- Approve/reject
- See errors
- Request fix
- Build
- Release
- Stop worker
- Roll back

Advanced code editing remains optional.
