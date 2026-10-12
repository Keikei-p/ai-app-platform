# Ivy cloud growth when the owner's PC is off

This is a **read-only cloud audit foundation**, not a claim that an AI agent
already writes and merges code independently.

## What is implemented on develop
- `.github/workflows/cloud-growth-audit.yml` checks out **develop** on a
  GitHub-hosted Linux runner, using `contents: read` permissions and
  `persist-credentials: false`.
- It checks selected source/Evidence attestations and runs regression tests
  for MissionStore, BuildJob restart recovery, and long-run Soak evidence.
- It writes no source code or user data, does not access local PC data, uses
  no paid LLM, and never bypasses approval.
- Cloud CI success is **not** proof of physical Windows restart, 24-hour Ivy
  runtime stability, commercial readiness, or automated source improvement.

## Important activation boundary

GitHub scheduled workflows run from the repository's **default branch only**.
The default branch of Keikei-p/ai-app-platform is currently `main`.
This workflow is **prepared on develop and is NOT scheduled yet**.
A repo owner must explicitly approve adding a minimal workflow entrypoint to
`main` or changing the default-branch architecture. Do not merge all of
`develop` into `main` to activate scheduling.

When an owner approves it, the recommended scheduler is an **independent,
read-only workflow on main** that checks out develop for testing. The cron
expression uses minute 17 rather than minute 0 to avoid overloaded times.
Schedules are best effort, not real-time SLAs, and may be delayed or skipped.

## Next iteration to reach real cloud code evolution

1. Add an owner-approved, least-privilege cloud AI worker (only after its
   provider, free limits and risk boundaries have been verified).
2. Feed it a bounded task chosen from CI failures or a reviewed backlog.
3. Work on an isolated ephemeral branch; run regressions and security checks.
4. Create a **draft PR** with exact diff and Evidence; do not auto-merge to
   main/develop, publish, spend money, or access owner credentials.
5. After the owner approves the automated-development policy, allow safe,
   low-risk changes to develop through a separate guarded gate. Production
   actions and protected boundaries always require approval.

GitHub Actions public-repository standard runners are generally free, but
service quotas and policies can change. Do not claim that unlimited LLM
inference or GPU-bound local Ollama is available on the GitHub runner.
