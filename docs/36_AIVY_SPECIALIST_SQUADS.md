# Aivy Specialist Squads

Aivy has a growing roster of specialist AI roles, but it should not call every role for every task.

## Current roster

Aivy currently defines 15 specialist roles:

1. Coordinator
2. Research
3. Architecture
4. Coding
5. Design
6. Test
7. Security
8. Build
9. Release
10. Database
11. Web
12. Mobile
13. Performance
14. Accessibility
15. DevOps

## Automatic squad selection

The SpecialistSquadSelector reads the user's goal and available project metadata.

Core engineering roles remain available:
- Architecture
- Coding
- Test
- Security

Optional specialists are added only when relevant. Examples:

- Firestore, SQL, persistence, migrations -> Database
- browser, website, Cloudflare, frontend -> Web
- Android, iOS, APK, IPA -> Mobile
- latency, startup, optimization -> Performance
- contrast, keyboard, ARIA, readability -> Accessibility
- deploy, CI/CD, cloud, monitoring, rollback -> DevOps
- build/package targets -> Build
- store/public production release -> Release

The full squad always includes Coordinator. Parallel sandbox workers are capped and exclude Build/Release because the parallel review layer is analysis-only.

## Why this matters

A large multi-agent system becomes weaker if every specialist talks on every task. Aivy therefore optimizes for the smallest useful squad:

- lower model cost
- less duplicated reasoning
- fewer contradictory recommendations
- clearer accountability
- faster parallel review
- easier audit history

## Safety

Squad selection changes who reviews a task. It does not grant new permissions.

Each specialist still has:
- an explicit role contract,
- a fixed tool allowlist,
- model routing through Aivy,
- evidence requirements,
- the same global safety and approval boundaries.

External publishing and release actions remain approval-gated.
