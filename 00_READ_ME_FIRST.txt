Aivy 0.8.0 - Windows 10/11 quick start
=======================================

[ZIP users: enable AUTO UPDATES only once]
    Double-click OPEN_AIVY_WEB.bat from the extracted ZIP folder.
    At the first prompt paste the HTTPS Git repository URL supplied by
    your distributor (for example https://github.com/account/repository.git).
    This creates %USERPROFILE%\Aivy-Latest (or Aivy-Latest-Git),
    keeping the old ZIP and AppData project database untouched.

    From then on double-click AIVY_WEB_SILENT.vbs in the installed folder.
    GitHub is checked automatically at each *cold server start*.
    If Ivy is already running, the shortcut opens that server instead;
    source updates are deferred until Ivy is stopped and relaunched.
    Offline or local changes: preserve the current installed version.
    The Git remote belongs to each buyer/owner, not the Ivy product.

[Most convenient] Double-click AIVY_DESKTOP_SILENT.vbs
    Opens the normal desktop GUI without flashing a BAT/PowerShell window.
    Safely updates source code from the Git branch when possible; no hard reset.
    The very first launch can take longer for Git fetch and readiness checks.

[When debugging] Double-click AIVY.bat
    Shows update/startup messages in a command window to investigate failures.

[Browser alternative] Double-click AIVY_WEB_SILENT.vbs
    Uses an existing local Aivy Web server or starts the browser UI.

[Full quality verification] Double-click CHECK.bat
    Runs the large unit/security/GUI/build/smoke suite separately.
    The ordinary START.bat now performs only critical readiness checks first.

[If problems occur] Double-click DIAGNOSTICS.bat
    Run SETUP.bat if Python 3.11+ is missing.

What to try:
    Chat -> explain the app you want -> review the plan -> confirm building
    -> verify the generated result -> request edits -> preview -> download.
    Builds, external publishing, payments and authorization still require
    the respective reviews and approvals.

Existing project data, chat histories, databases, secrets and backups
remain in %LOCALAPPDATA%\AI-App-Platform. Safe Git updates must not
overwrite runtime data or local source edits.

Only one Tk desktop GUI runs per Windows logon session. An existing GUI is
not killed when a second shortcut is opened. The web UI runs separately.

Ivy running only on a PC cannot continue working after the PC powers off.
24-hour continuous operation and recovery after a real physical Windows
reboot require separate validation. Passing CI is not proof of those claims.
