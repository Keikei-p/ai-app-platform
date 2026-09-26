@echo off
setlocal EnableExtensions
title AI App Platform - Install or Update

set "REPO=https://github.com/Keikei-p/ai-app-platform.git"
set "DEST=%USERPROFILE%\AI-App-Platform-Git"

echo.
echo ==========================================
echo   AI App Platform - Install / Update
echo ==========================================
echo.
echo Install folder:
echo   %DEST%
echo.

where git >nul 2>nul
if errorlevel 1 goto :no_git

if exist "%DEST%\.git" goto :update
if exist "%DEST%" goto :folder_exists

echo [1/3] Downloading latest stable version...
git clone --branch main --single-branch "%REPO%" "%DEST%"
if errorlevel 1 goto :failed

goto :verify

:update
echo [1/3] Updating existing Git installation...
git -C "%DEST%" fetch origin main
if errorlevel 1 goto :failed
git -C "%DEST%" checkout main
if errorlevel 1 goto :failed
git -C "%DEST%" reset --hard origin/main
if errorlevel 1 goto :failed

goto :verify

:folder_exists
echo.
echo ERROR: The destination folder already exists but is not a Git installation.
echo Folder:
echo   %DEST%
echo.
echo Rename or remove that folder, then run this file again.
pause
exit /b 1

:verify
echo.
echo [2/3] Verifying installed version...
if not exist "%DEST%\VERSION" goto :failed
set "APP_VERSION="
set /p APP_VERSION=<"%DEST%\VERSION"
echo Installed: v%APP_VERSION%

echo.
echo [3/3] Starting AI App Platform...
cd /d "%DEST%"
call START.bat
exit /b %errorlevel%

:no_git
echo.
echo ERROR: Git was not found.
echo Git is required to install/update AI App Platform.
pause
exit /b 1

:failed
echo.
echo ERROR: Install/update failed.
echo Your existing user data under %%LOCALAPPDATA%%\AI-App-Platform was not deleted.
pause
exit /b 1
