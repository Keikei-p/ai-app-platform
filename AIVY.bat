@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Aivy - Latest Launcher

set "CHANNEL=develop"
if /I "%AIVY_CHANNEL%"=="main" set "CHANNEL=main"
if /I "%AIVY_CHANNEL%"=="develop" set "CHANNEL=develop"
if /I "%~1"=="stable" set "CHANNEL=main"
if /I "%~1"=="latest" set "CHANNEL=develop"

echo.
echo ==========================================
echo   Aivy - Safe Auto Update Launcher
echo ==========================================
echo Channel: %CHANNEL%
echo.

if /I "%~1"=="--skip-update" goto :launch

where git >nul 2>nul
if errorlevel 1 goto :git_missing
if not exist ".git\" goto :not_git

set "DIRTY="
for /f "delims=" %%I in ('git status --porcelain --untracked-files=all 2^>nul') do set "DIRTY=1"
if defined DIRTY goto :local_changes

set "BEFORE_SHA="
for /f %%I in ('git rev-parse HEAD 2^>nul') do set "BEFORE_SHA=%%I"

echo [1/3] Checking GitHub...
git fetch --prune origin "+refs/heads/%CHANNEL%:refs/remotes/origin/%CHANNEL%"
if errorlevel 1 goto :update_failed

set "CURRENT_BRANCH="
for /f "delims=" %%I in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "CURRENT_BRANCH=%%I"

echo [2/3] Selecting %CHANNEL%...
if /I not "!CURRENT_BRANCH!"=="%CHANNEL%" (
    git checkout "%CHANNEL%"
    if errorlevel 1 goto :update_failed
)

echo [3/3] Applying safe fast-forward update...
git merge --ff-only "origin/%CHANNEL%"
if errorlevel 1 goto :update_failed

if not exist ".aivy" mkdir ".aivy" >nul 2>nul
if defined BEFORE_SHA >".aivy\previous_commit.txt" echo !BEFORE_SHA!
for /f %%I in ('git rev-parse HEAD 2^>nul') do >".aivy\current_commit.txt" echo %%I
>".aivy\channel.txt" echo %CHANNEL%

echo Aivy is up to date.
goto :launch

:local_changes
echo.
echo Local code changes were detected.
echo Auto-update was skipped so your work is not overwritten.
echo Commit, stash, or revert those changes when you want automatic updating again.
goto :launch

:git_missing
echo.
echo Git was not found. Starting the current Aivy copy without updating.
goto :launch

:not_git
echo.
echo This folder is not a Git checkout.
echo Starting the current copy without updating.
goto :launch

:update_failed
echo.
echo Automatic update could not be completed safely.
echo No hard reset was performed. Starting the current copy instead.
goto :launch

:launch
echo.
echo Starting Aivy...
call START.bat
exit /b %errorlevel%
