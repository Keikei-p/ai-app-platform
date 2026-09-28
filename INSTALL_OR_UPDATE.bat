@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Aivy - Install or Update

set "REPO=https://github.com/Keikei-p/ai-app-platform.git"
set "DEST=%USERPROFILE%\AI-App-Platform-Git"
set "CHANNEL=develop"

if /I "%AIVY_CHANNEL%"=="main" set "CHANNEL=main"
if /I "%AIVY_CHANNEL%"=="develop" set "CHANNEL=develop"
if /I "%~1"=="stable" set "CHANNEL=main"
if /I "%~1"=="latest" set "CHANNEL=develop"

echo.
echo ==========================================
echo   Aivy - Install / Safe Update
echo ==========================================
echo Channel:
echo   %CHANNEL%
echo Install folder:
echo   %DEST%
echo.

where git >nul 2>nul
if errorlevel 1 goto :no_git

if exist "%DEST%\.git" goto :update
if exist "%DEST%" goto :folder_exists

echo [1/3] Downloading Aivy...
git clone --branch "%CHANNEL%" "%REPO%" "%DEST%"
if errorlevel 1 goto :failed
goto :verify

:update
echo [1/3] Checking existing Git installation...
set "DIRTY="
for /f "delims=" %%I in ('git -C "%DEST%" status --porcelain --untracked-files=all 2^>nul') do set "DIRTY=1"
if defined DIRTY goto :local_changes

git -C "%DEST%" fetch --prune origin "+refs/heads/%CHANNEL%:refs/remotes/origin/%CHANNEL%"
if errorlevel 1 goto :safe_update_failed

git -C "%DEST%" checkout "%CHANNEL%"
if errorlevel 1 goto :safe_update_failed

git -C "%DEST%" merge --ff-only "origin/%CHANNEL%"
if errorlevel 1 goto :safe_update_failed
goto :verify

:local_changes
echo.
echo Local code changes were detected.
echo Update was skipped so those changes are not overwritten.
echo Starting the currently installed copy.
goto :start_existing

:safe_update_failed
echo.
echo The repository could not be fast-forwarded safely.
echo No hard reset was performed.
echo Starting the currently installed copy.
goto :start_existing

:folder_exists
echo.
echo ERROR: The destination folder already exists but is not a Git installation.
echo Folder:
echo   %DEST%
echo.
echo Rename that folder once, then run this file again.
pause
exit /b 1

:verify
echo.
echo [2/3] Verifying installed version...
if not exist "%DEST%\VERSION" goto :failed
set "APP_VERSION="
set /p APP_VERSION=<"%DEST%\VERSION"
echo Installed platform version: v%APP_VERSION%

:start_existing
echo.
echo [3/3] Starting Aivy...
cd /d "%DEST%"
if exist AIVY.bat (
    call AIVY.bat --skip-update
) else (
    call START.bat
)
exit /b %errorlevel%

:no_git
if exist "%DEST%\START.bat" (
    echo.
    echo Git was not found. Starting the installed copy without updating.
    cd /d "%DEST%"
    call START.bat
    exit /b %errorlevel%
)
echo.
echo ERROR: Git was not found.
echo Git is required for the first Aivy installation.
pause
exit /b 1

:failed
echo.
echo ERROR: Install/update failed.
echo Existing user data under %%LOCALAPPDATA%%\AI-App-Platform was not deleted.
pause
exit /b 1
