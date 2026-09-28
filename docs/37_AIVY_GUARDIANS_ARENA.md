# Aivy Guardians, Candidate Arena, and Measured Model Learning

Aivy now adds deterministic quality guardians around the existing build, recovery,
certificate, learning, Mission Control, and specialist systems.

## Guardians

### Regression Guardian
Compares the pre-change and post-change EvaluationReports.

Completion is blocked if a gate that previously passed becomes failing:
- tests
- security
- design
- preview readiness

A score drop without a critical gate regression is recorded as a warning.

### Requirement Guardian
Creates a requirement-to-evidence ledger from the AppSpec, user instruction,
postflight evidence, and execution trace.

It intentionally does **not** claim semantic feature completion merely because
the overall pipeline passed. Feature rows remain evidence-backed but may require
semantic review. Missing structural specification data can block completion.

### Dependency Guardian
Performs offline dependency-hygiene checks for Python and npm manifests.

It can identify:
- unpinned Python dependencies
- mutable/remote Python dependency sources
- npm wildcard/latest dependencies
- remote/local mutable npm dependency sources

It does not claim live CVE coverage. A live advisory source would be required for
fresh vulnerability assertions.

### Accessibility Guardian
Performs deterministic static HTML checks such as:
- html language
- image alt text
- accessible button names
- form ids and labels

High-severity deterministic accessibility failures can block completion.
This is not a claim of full WCAG conformance.

### Performance Guardian
Records static source size, largest text asset, and asset count against bounded
budgets. It does not claim runtime latency unless runtime measurement exists.

## Project Memory

Successful certified builds are recorded into project-local verified memory.
This sits alongside Aivy's global verified learning so each app can preserve its
own design and implementation history.

## Candidate Arena v1

Candidate Arena compares multiple already-evaluated candidate outcomes against
one baseline.

A candidate is eligible only when it:
- improves the baseline score,
- keeps tests passing,
- keeps security passing,
- keeps design passing,
- keeps preview readiness,
- introduces no critical regression.

The Arena may identify a winner candidate, but `auto_apply` is always false.
Application still requires the reviewed writer and human approval boundaries.

## Model Benchmark Store

Aivy records measured model outcomes from verified build runs:
- capability
- provider/model
- success
- quality score
- optional latency
- optional cost
- evidence reference

The benchmark dashboard orders only measured observations. An unmeasured model
is never declared better.

## Health Dashboard

Aivy Health summarizes projects, specialists, missions, verified learning, and
model observations. It is an operational view, not a substitute for project-level
quality evidence.

## Remaining external-infrastructure work

The following are not falsely marked complete:
- cloud execution while the user's PC is powered off
- real interactive browser/computer control beyond the current reviewed browser capture
- live package vulnerability feeds
- store signing/submission without explicit human approval
- full autonomous candidate-writing worktrees with conflict-safe patch promotion
