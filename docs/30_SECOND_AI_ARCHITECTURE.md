# v0.9+ — Second AI Architecture

## Mission

AI App Platform is evolving from an app generator into a policy-bounded development agent.

The target is not an unconstrained self-modifying AI. The target is an AI development system that can:

1. understand a goal
2. inspect the current project and prior verified outcomes
3. decompose work into bounded steps
4. choose approved tools
5. generate and modify code
6. test and inspect evidence
7. repair bounded failures
8. explain what changed
9. package verified artifacts
10. stop for human approval before consequential external actions
11. learn only from verified outcomes

## Non-negotiable safety properties

- No generic arbitrary shell tool exposed to the model.
- No bypass of Safety Gate, permissions, tests, Design AI, Security Self-Check, release approval, or store approval.
- Maximum bounded automatic repair attempts.
- Agent completion requires external evidence; the model cannot declare itself complete.
- Unverified guesses do not enter reusable Agent Memory.
- Secrets are redacted before learning storage.
- Local Platform API remains loopback-only.
- Production publishing, billing, signing, destructive operations, credential export, and store submission remain explicit-human-approval operations.

## v0.9 foundation

### Core/UI separation

Python remains the authoritative Core Engine.

UI clients use PlatformService / Platform API rather than importing Tkinter internals.

Target clients:

- legacy Tkinter desktop shell during migration
- v0.9 Web UI
- future Tauri Windows/macOS desktop shell
- future browser-based local UI
- future mobile management client

### Agent Orchestrator

The bounded development loop is:

understand
→ inspect
→ plan
→ generate
→ validate
→ repair
→ package
→ human review when required
→ evidence-backed report

### Evidence Ledger

Every important autonomous run should be able to point to evidence such as:

- plan
- source changes
- test results
- Design AI report
- Security report
- artifact checksum
- build output
- human approval state

Completion without the required evidence is blocked.

### Verified Agent Memory

Agent Memory stores lessons only when the source is verified.

Examples:

- generation-pipeline PASS
- deterministic test failure
- verified Design AI failure
- security finding
- user-approved correction outcome

Unverified model speculation is not promoted into reusable lessons.

## v0.9.1 — Web UI migration

- conversation-first Web Shell
- responsive sidebar/drawer
- conversations
- projects
- project detail
- downloads
- settings
- Agent Plan inspector
- build approval
- progress streaming
- real-time logs
- artifact actions

Tkinter remains available until the Web UI passes equivalent acceptance tests.

## v0.9.2 — Visual Design AI

Pipeline:

launch preview
→ capture mobile/tablet/desktop screenshots
→ deterministic layout checks
→ vision-model critique
→ structured findings
→ bounded source repair
→ recapture
→ comparison
→ quality evidence

The visual model may recommend code changes, but it cannot lower the design/security/test gate to pass itself.

## v0.9.3 — Tool Registry

All agent tools become explicit registered capabilities.

Each tool declares:

- name
- purpose
- input schema
- read/write scope
- risk class
- whether human approval is required
- evidence emitted
- timeout/retry policy

No model-generated tool name is executed unless registered.

## v0.9.4 — Model Router

A provider-neutral AI interface chooses models by task.

Possible routing:

- fast/cheap model: classification, summarization, simple transformations
- strong coding model: code generation and repair
- vision model: visual review
- strong reasoning model: architecture/security review
- local model: offline/privacy-first tasks when supported

Routing decisions must remain inspectable and cost-limited.

## v0.9.5 — Autonomous Evaluation Loop

Every development run receives objective metrics:

- tests passed
- design score
- security findings
- capability completeness
- build success
- artifact existence/checksum
- repair count
- time/cost
- user correction after completion

The platform can compare verified outcomes and improve future planning without modifying safety policy.

## v0.9.6 — Build and Release Manager

Windows:
- executable
- installer
- signing readiness
- update manifest

Android:
- debug APK
- release APK/AAB
- signing readiness
- Play Console submission preparation

iOS:
- source/bundle
- macOS/Xcode build runner
- signing readiness
- IPA archive
- App Store submission preparation

External release remains human-approved.

## v0.9.7 — Deployment Manager

Approved adapters can prepare/deploy to providers such as:

- Cloudflare
- GitHub Pages
- Firebase Hosting
- Vercel/Netlify where configured

The model never invents credentials and cannot publish without approval.

## v0.9.8 — Plugin Architecture

Provider/app integrations become modules rather than hard-coded core logic.

Example areas:

- Firebase
- Supabase
- Stripe
- WordPress
- Cloudflare
- YouTube
- Instagram/Threads
- GitHub

Plugins must use explicit permissions and schemas.

## v0.9.9 — Autonomous Development Acceptance

A release candidate must prove an end-to-end flow:

natural-language goal
→ spec
→ human approval
→ implementation
→ tests
→ security
→ screenshot review
→ repair
→ preview
→ artifact
→ download
→ evidence-backed completion

## v1.0

v1.0 means the platform can safely carry a normal supported app from conversation to a verified usable artifact with a clear history and evidence trail.

It does not mean every possible app, platform, external API, legal requirement, or store workflow is universally solved.

## Definition of “Second AI”

For this project, “Second AI” means the platform behaves like a persistent development partner rather than a one-shot code generator:

- remembers verified project experience
- has a model of current project state
- plans multi-step work
- uses approved tools
- checks its own output with independent evidence
- repairs bounded errors
- communicates uncertainty
- preserves history
- respects approvals
- learns from verified outcomes

It must never mean “trust the AI because it says it improved itself.”
