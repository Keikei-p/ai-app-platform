# Change safety foundation

The existing chat build route now runs `change.prepare` during AgentPlanRunner preflight, before AICore changes source. No UI buttons or login system were added.

## Contracts

- `ProjectUnderstandingAI.analyze(root)` inventories bounded local files, hashes readable files, resolves static Python imports, lists dependency names and package script names, and identifies likely features, DB, authentication, tests, build and protected files. It never executes project scripts. Classification is heuristic, not semantic certainty.
- `ChangeImpactAnalyzer.analyze(map, request, changed_paths)` walks reverse Python dependencies transitively and requests the full discovered test suite plus build/security checks. Explicit paths in a request can seed analysis. Unresolved targets and unsupported/new source paths are YELLOW, not assumed safe. DB/auth/dependency changes are YELLOW. Protected files, credential paths and high-risk request keywords are RED. This is a conservative foundation, not a complete natural-language risk classifier.
- `CheckpointManager.create(root)` snapshots source before mutation with per-file SHA-256 and a manifest digest recorded in Evidence. Budgets: 10,000 files, 64 MiB per checkpoint. Linked paths are rejected. Concurrent edits detected during capture fail closed.
- `checkpoint.restore` requires explicit tool approval and the original manifest digest. It checks inventory, hashes and RootPolicyGuard, then recovers into a new `.aiapp/recoveries/<id>` tree. It preserves current work. Core exceptions or failed core/postflight/trace validation automatically create a recovery tree through the same manager.

The last Project Map, impact and checkpoint reference are persisted in `.aiapp/reports/change_preparation.json`; Evidence contains the checkpoint ID and manifest digest. `.aiapp/agent/runs` retains the existing redacted execution summaries. Analysis success is not test success or evidence of product completion. Existing postflight and completion gates remain in force.

RootPolicyGuard and Evolution Engine share the protected-path policy; this change adds the new safety implementation and executor/runner to that protected set. RED cannot be overridden by a generic approved flag on `change.prepare`; route such requests through human review outside autonomous generation.

## Boundaries

- Python static imports only; dynamic imports and non-Python dependency graphs require further analysis. DB/auth identification is based on filenames. Build file/script discovery does not establish that a build works.
- YELLOW emits a review requirement and continues through existing tests/design/security postflight. An independent Reviewer gate is future work.
- Recovery does **not** automatically replace the active project. It provides verified pre-change source for review/switching. Git internals, `.aiapp`, vaults, dependency directories and build artifacts are excluded. No consistent backup of live databases or external services is claimed.
- Local checkpoints can contain source configuration; they are local plaintext, not a secrets vault. Retention/cleanup, concurrency locking against hostile writers, remote backup and signed evidence remain future work.

## Verification

`python -m unittest discover -s tests -v` includes transitive impact, conservative risk, checkpoint restore after modification/deletion, tamper rejection, path traversal, real preflight Evidence, RED blocking and approval tests. CI already discovers this test file. Run `python -m src.tools.security_selfcheck` plus the existing acceptance tools. Only actual passing checks count toward completion.
