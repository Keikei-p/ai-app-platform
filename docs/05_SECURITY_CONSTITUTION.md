# Security Constitution

These rules sit above the AI and cannot be modified by AI-generated code.

## Immutable rules

1. AI cannot disable Safety Gate.
2. AI cannot grant itself additional privileges.
3. AI cannot erase all audit history.
4. AI cannot erase all backups/restore points.
5. AI cannot reveal/export secrets without an explicit authorized flow.
6. AI cannot expose the local worker directly to the public internet by default.
7. Production deploy, destructive DB operations, billing changes, domain changes and store submissions require explicit approval until policy says otherwise.
8. A failed health check after release triggers stop/rollback logic rather than repeated blind changes.
9. Secrets are isolated from prompts, logs and generated source wherever possible.
10. Every autonomous action must be attributable, reviewable and reversible when technically possible.

## Approval classes

- A0: read-only, diagnostics
- A1: local reversible edit/test
- A2: external non-production action
- A3: production deploy / domain / billing / store submit
- A4: destructive/irreversible/high-risk action

A3/A4 require explicit human approval by default.
