# Ivy Windows restart recovery: safe activation and verification

This capability is **opt-in**. Updating Ivy does not register an autostart task,
change Windows settings, launch paid services, or bypass build approval.

## Current behavior

- `ENABLE_AIVY_AUTOSTART.vbs` creates **one** current-user shortcut in the Windows
  Startup folder after the user runs it. It does not require administrator access.
- The shortcut launches `AIVY_WEB_SILENT.vbs` when that user **signs in**.
  It prefers the install directory containing the launcher and falls back to
  known legacy directory names, without hardcoded developer accounts.
- `DISABLE_AIVY_AUTOSTART.vbs` removes **only** an exact matching Ivy shortcut,
  when explicitly launched. It never deletes workspaces or application data.
- If an unrelated shortcut with the same name exists, neither script overwrites
  or removes it. Re-running the enable script is idempotent.
- Build history lives in the user state directory under
  `data/aivy_build_jobs.json`; no source, raw result, token, or exception
  details are saved there.
- Interrupted builds remain an audit record marked `failed/interrupted`.
  **No builds are automatically retried or approved.** Mission recovery still
  requires normal preflight and explicit approval before any new build.
- `build_watchdog_status()` reports active, stalled and interrupted jobs and
  storage errors. It does **not** kill or re-run workers.

## Manual acceptance on a real Windows PC (not yet certified by CI)

1. Install/update the Git checkout normally and run `AIVY_WEB.bat` once.
   Verify the local web UI works and that no sensitive fields are printed.
2. Explicitly run `ENABLE_AIVY_AUTOSTART.vbs`. Check the current user's Startup
   folder for **Ivy Web Autostart**. Do not run it as administrator.
3. Make a disposable test workspace. Start a test Mission, get to a safe
   pause/review point, and record its Mission ID and evidence references.
4. Sign out and sign back in, or perform a **user-authorized** Windows restart.
   Verify the local web UI is reachable. Check that Mission state and evidence
   remain, and interrupted builds are labeled as interrupted.
5. Confirm that no build runs without a new explicit approval. Check
   `build_watchdog_status()` for unexpected errors.
6. Run `DISABLE_AIVY_AUTOSTART.vbs` if this PC should no longer start Ivy
   when the user signs in. Verify no workspace or saved Mission was removed.

**Limitations:** Windows Startup runs only after user sign-in, not before login;
sleep/hibernation, Windows Update restarts, another process instance and power
loss still need real-device fault-injection tests. The script alone is not
evidence of a successful physical Windows reboot.

## 24-hour stability gate

The existing `LongRunSoakMonitor` starts its background checkpointing with the
service (15-minute target cadence). A verified result requires at least 24 **real**
hours, enough healthy samples, no excessive gaps, and unchanged monitored source
files. Fake-clock unit tests do not count as a real-world pass.

To certify 24-hour stability, use an already running Ivy installation, inspect
the live soak status and its persisted evidence after 24 hours, and record the
real start/end times, failure count and gap conditions. Do not label this
criterion complete merely because the timer or unit tests can be simulated.

## Sale/transfer release gate

Ivy already provides `BuyerJourneyE2EVerifier` for an isolated no-network
buyer journey: clean first boot, own connectors, secret-free export/import,
reauthentication, OEM ownership reset and safe transfer package. The CI test
`tests/test_productization_buyer_journey_e2e.py` exercises that flow.
Generated Windows/mobile/Android acceptance workflows verify additional build
artifacts. A commercial release still requires **all** of the following:

- Passing latest source-bound buyer-journey and artifact acceptance evidence
- Verified uninterrupted 24-hour soak, and real Windows sign-in/reboot trial
- Signed release/distribution review and separate buyer-owned credentials
- Human approval for pricing, license terms, code signing and publication

None of those commercial actions are performed by these scripts.
