# Aivy Learning Flywheel

Aivy grows from verified outcomes, not from raw model output.

## Goal

Turn successful app-development runs into reusable, inspectable learning evidence while keeping model training, policy changes, publishing, and main-branch changes under separate review.

## Flow

1. A user requirement enters the normal Aivy build flow.
2. Existing safety, change-impact, checkpoint, generation, test, design, security, postflight, execution-trace, recovery-review, and Development Certificate gates run.
3. Only if the final result is successful and the Evaluation Engine marks it `learning_eligible`, the Learning Flywheel may capture it.
4. The captured item stores a redacted requirement, outcome summary, quality vector, model route, repair count, evidence references, and hashes of safe source files.
5. A verified lesson is added to Development Memory so similar future work can reuse it.
6. Supervision candidates are available for a future Aivy-specific model-training pipeline.

## Safety properties

- Failed builds are never accepted as successful supervision.
- A build without verification evidence is rejected.
- Secrets and known sensitive/binary files are excluded from source manifests.
- Source code is not copied into the global learning store; safe file paths and SHA-256 fingerprints are retained as references.
- Duplicate verified runs are deduplicated.
- Learning does not weaken Safety Gate, approval, testing, or root policy.
- Learning does not automatically fine-tune a model.
- Learning does not automatically merge or publish code.

## Current stage

The current stage is **collecting verified supervision**.

This is intentionally earlier than automatic fine-tuning. The objective is to build a clean, evidence-backed corpus first. Once enough diverse verified examples exist, Aivy can add offline dataset review, benchmark splits, small-model fine-tuning experiments, and candidate-vs-baseline evaluation behind the existing Evolution and human-review gates.
