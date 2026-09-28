# Aivy Parallel Sandbox Workers

Aivy uses isolated filesystem snapshots for parallel specialist review before a single reviewed writer changes the live project.

## Why

Parallel agents can improve coverage and reduce wall-clock time, but allowing several workers to write the same project concurrently creates race conditions, conflicting edits, and hard-to-audit failures.

Aivy therefore separates:
- control plane: Mission Control, approval, audit, model routing, evidence
- worker plane: isolated per-role project snapshots
- write plane: the existing single reviewed build pipeline

## v1 roles

The default parallel review uses:
- Research
- Architecture
- Coding
- Test
- Design
- Security

Each role receives its own copied snapshot and an independent one-model-call budget.

## Isolation properties

- Every worker receives a distinct filesystem copy.
- The live source project is never passed as a writable worker workspace.
- Secret-style files such as .env, keys, certificates, databases, .git data, node_modules, artifacts, and Aivy internal evidence folders are excluded.
- Snapshot size and per-file size are bounded.
- No sandbox worker receives shell execution.
- No sandbox worker receives network tools through this layer.
- Requested specialist tools are advisory only in this parallel layer.
- The live project is fingerprinted before and after the run.
- A source fingerprint change blocks the parallel review result.
- Temporary worker copies are deleted when the run finishes.
- A redacted summary is saved under the project's Aivy evidence directory.

## Coordinator rule

Parallel workers do not merge code.

Their findings feed Mission Control and the reviewed execution council. Actual code generation remains a single-writer operation through Aivy's existing checkpoints, safety gate, tests, recovery, certificate, and learning pipeline.

## Future evolution

The next step beyond read-only snapshot workers is isolated candidate-writing sandboxes:
1. give each coding candidate a separate Git worktree/container,
2. run tests and security independently inside each candidate,
3. compare candidates against the same benchmark,
4. let the coordinator select or synthesize only verified changes,
5. apply the winning patch through the single reviewed writer.

That stage should not be enabled until deterministic candidate comparison and conflict-safe patch promotion are implemented.
