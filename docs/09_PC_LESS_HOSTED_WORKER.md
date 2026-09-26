# PC-less / Hosted Worker Architecture

## Goal

スマホしか持っていない人でも、Home PC Workerと同じユーザー体験を提供する。

## Abstraction

UI sends a Job to a Worker API. The UI does not care whether the Worker is:

- Home PC
- Hosted compute
- Enterprise server

## Hosted Worker safety

Each job must run isolated from other customers. Required design areas:

- sandbox/container isolation
- ephemeral workspace
- secrets injection without logging
- resource/time limits
- outbound network policy
- malware/abuse controls
- artifact scanning
- cleanup after job
- encrypted storage
- per-tenant authorization

## Commercial implication

Hosted Worker consumes real compute/storage/network resources, so it cannot be unlimited free. Home PC Worker can remain the lowest-cost path while Hosted Worker becomes paid/metered.
