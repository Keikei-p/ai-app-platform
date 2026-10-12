# Ivy: fastest safe desktop startup (Windows)

To launch the existing desktop GUI with no extra console window, double-click
`AIVY_DESKTOP_SILENT.vbs` in the installed Ivy Git folder. It calls the
existing `AIVY.bat` safe auto-update then starts the desktop GUI.

`START.bat` now runs **basic readiness checks only** before showing the chat.
It intentionally does not run 500+ unit tests on each launch. For **all**
unit, regression, GUI, security and smoke checks run `CHECK.bat` or CI.
The AI provider still needs valid connection settings for cloud chat; nothing
about the launcher bypasses approvals, requests payment or publishes a build.

Only one desktop instance runs per Windows sign-in session. Repeated shortcut
clicks do not create another Tk window or start another local GUI worker pool.
The named mutex closes automatically when the process ends (including a crash).
The web UI can still be used separately.

If the program cannot start: run `DIAGNOSTICS.bat` and share the **redacted**
diagnostic results. The runtime workspace, local database, build history,
credentials and backups remain under `%LOCALAPPDATA%\AI-App-Platform`.
No user data is reset during this startup change.

This change is subject to Windows GitHub CI and real desktop acceptance.
A passing CI does not certify the user's physical Windows installation.
