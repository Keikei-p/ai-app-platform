# Aivy Mission Control

Mission Control is Aivy's persistent long-horizon execution layer.

## Purpose

Aivy already has bounded plans, reviewed tools, checkpoints, specialist agents,
recovery supervision, evidence-backed completion, and a verified learning loop.
Mission Control adds a durable lifecycle around that work so a goal can survive
interruptions without losing its state.

## v1 lifecycle

planned -> preflight -> approval_required -> build_running -> completed

A mission may also enter paused, failed, cancelled, or resume_required.

Each mission keeps:
- goal
- project
- plan snapshot
- current phase
- cycle budget
- approval state
- build job reference
- evidence references
- transition history
- final result summary

## Safety

Mission Control does not replace existing Aivy gates.

- Preflight uses the reviewed AgentPlanRunner.
- Code generation still requires explicit approval.
- Existing checkpoints and recovery remain authoritative.
- Active writes are not cancelled in the middle of a build.
- Restarted running missions recover to a paused/resumable state.
- A bounded cycle budget prevents silent infinite loops.
- Publishing, signing, store submission, and main-branch changes keep their existing approval rules.

## Honest current boundary

Mission Control v1 is durable local orchestration.

It does not mean:
- a powered-off PC keeps computing,
- a process-local build automatically survives an abrupt process kill,
- multiple coding workers are already isolated in independent worktrees,
- Aivy can bypass human approval for consequential external actions.

If the process ends during a build, the mission record survives and Aivy requires
a safe reinspection before continuing.

## Next frontier

The next stages are:
1. isolated Git worktrees or containers per worker,
2. parallel mission workers with project-level write locks,
3. durable cloud execution for jobs that must continue while the PC is off,
4. mid-flight steering without losing mission state,
5. benchmark-driven model and specialist selection,
6. automatic regression comparison before accepting an agent improvement.
