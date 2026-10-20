@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
title Ivy Web - Auto Update Setup

echo.
echo ============================================
echo  Ivy Web - One-time setup / auto updates
echo ============================================
echo.
echo The first setup converts a ZIP copy into a safe Git installation.
echo Existing projects, chats and database are NOT replaced.
echo Later launches from AIVY_WEB_SILENT.vbs update automatically.
rem AIVY_UPSTREAM_REPO can be set by the owner; Python validates it before clone.
echo.

where git >nul 2>nul
if errorlevel 1 goto :git_missing

set "PY="
python -c "import sys;raise SystemExit(sys.version_info < (3,11))" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto :install
py -3 -c "import sys;raise SystemExit(sys.version_info < (3,11))" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY goto :python_missing

:install
%PY% -m src.tools.ivy_bootstrap --source-folder "%~dp0."
if errorlevel 1 goto :failed

set "DEST=%USERPROFILE%\Aivy-Latest"
if exist "%DEST%\.git\" goto :launch
set "DEST=%USERPROFILE%\Aivy-Latest-Git"
if not exist "%DEST%\.git\" goto :failed

:launch
if not exist "%DEST%\AIVY_WEB_SILENT.vbs" goto :outdated_launcher
echo.
echo [OK] Opening the installed Ivy Web...
echo       Next time, just double-click AIVY_WEB_SILENT.vbs
echo       in %DEST%
echo       If the web server is already running, updates are deferred.
start "" "%WINDIR%\System32\wscript.exe" "%DEST%\AIVY_WEB_SILENT.vbs"
exit /b 0

:outdated_launcher
echo.
echo [NOTICE] This Git installation is older and has no silent launcher yet.
echo          Nothing was deleted, and no source files were overwritten.
echo          Checking whether Ivy Web is already running...
%PY% -m src.tools.ivy_bootstrap --probe-web
if errorlevel 1 goto :need_cold_update
echo [OK] Ivy Web is already running. Opening it in your browser.
start "" "http://127.0.0.1:8766/"
echo [UPDATE PENDING] Exit the running Ivy Web server, then
echo                  run OPEN_AIVY_WEB.bat again to update the launcher.
exit /b 0

:need_cold_update
echo [UPDATE PENDING] The silent launcher is missing.
echo                  Close Ivy Web if it is running, then rerun this installer.
echo                  Never delete the workspace or AppData folder.
pause
exit /b 1

:git_missing
echo Git for Windows is required for safe automatic updates.
echo Install Git from https://git-scm.com/download/win
goto :failed

:python_missing
echo Python 3.11 or later was not found.
echo Run SETUP.bat or install Python and retry.
goto :failed

:failed
echo.
echo Ivy was not installed or started. Existing project data was not deleted.
pause
exit /b 1
