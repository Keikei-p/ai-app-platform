# Development workflow

`Keikei-p/ai-app-platform` is the source of truth for AI App Platform.

## Branches

- `main`: stable, tested code only.
- `develop`: active integration branch.
- `feature/*`: larger isolated changes branched from `develop`.

Do not commit runtime/user data, generated projects, logs, backups, API keys, credentials, certificates, signing keys, or store credentials.

## Before merging to main

Run:

```bash
python -m compileall -q src tests
python -m src.tools.security_selfcheck
python -m unittest discover -s tests -v
python -m src.tools.acceptance_test
python -m src.tools.remote_acceptance_test
python -m src.tools.smoke_test
```

GUI acceptance and real-device checks remain release gates and are not replaced by CI.

## Versioning and releases

`VERSION` is the single source for the application version. Normal development does not create ZIP or `.aipupdate` files. A distributable Windows build is created only from a version tag such as `v0.5.1` or `v1.0.0`.

Release flow:

1. Develop and test on `develop` / `feature/*`.
2. Merge a verified build to `main`.
3. Update `VERSION` and release notes.
4. Tag the exact `main` commit.
5. GitHub Actions builds the Windows package and publishes it to GitHub Releases.

Future in-app updates should consume signed release artifacts, verify them, back up user state, update, run post-update checks, and roll back on failure.
