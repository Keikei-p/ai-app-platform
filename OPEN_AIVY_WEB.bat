@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Aivy Web - One Click
set "REPO=%AIVY_UPSTREAM_REPO%"
set "DEST=%USERPROFILE%\Aivy-Latest"
set "CHANNEL=develop"

echo.
echo ==========================================
echo   Aivy Web - One Click
echo ==========================================
echo.
echo Aivy will be installed or updated safely.
echo Install folder:
echo   %DEST%
echo.

where git >nul 2>nul
if errorlevel 1 goto :repo_missing
echo.
echo No update source is configured.
echo For a buyer/OEM installation, use the delivered Ivy package.
echo For a Git-based installation, set AIVY_UPSTREAM_REPO to your own repository URL.
pause
exit /b 1

:git_missing

if exist "%DEST%\.git" (
    if not defined REPO for /f "delims=" %%I in ('git -C "%DEST%" remote get-url origin 2^>nul') do set "REPO=%%I"
    goto :update
)
if not defined REPO goto :repo_missing
if exist "%DEST%" goto :choose_new_folder

echo [1/3] Installing latest Aivy...
git clone --branch "%CHANNEL%" "%REPO%" "%DEST%"
if errorlevel 1 goto :failed
goto :start

:choose_new_folder
set "DEST=%USERPROFILE%\Aivy-Latest-Git"
if exist "%DEST%\.git" goto :update
if exist "%DEST%" goto :folder_problem
echo [1/3] Installing latest Aivy in a clean folder...
git clone --branch "%CHANNEL%" "%REPO%" "%DEST%"
if errorlevel 1 goto :failed
goto :start

:update
echo [1/3] Checking for the latest Aivy...
set "DIRTY="
for /f "delims=" %%I in ('git -C "%DEST%" status --porcelain --untracked-files=all 2^>nul') do set "DIRTY=1"
if defined DIRTY goto :dirty

git -C "%DEST%" fetch --prune origin "+refs/heads/%CHANNEL%:refs/remotes/origin/%CHANNEL%"
if errorlevel 1 goto :safe_update_failed
git -C "%DEST%" checkout "%CHANNEL%"
if errorlevel 1 goto :safe_update_failed
git -C "%DEST%" merge --ff-only "origin/%CHANNEL%"
if errorlevel 1 goto :safe_update_failed
goto :start

:dirty
echo.
echo Local code changes were found, so Aivy will not overwrite them.
echo The currently installed copy will be opened.
goto :start

:safe_update_failed
echo.
echo The latest version could not be applied safely.
echo No files were force-deleted. The current copy will be opened.
goto :start

:start
echo [2/3] Preparing Aivy Web...
if not exist "%DEST%\AIVY_WEB.bat" goto :failed
echo [3/3] Opening Aivy Web...
cd /d "%DEST%"
call AIVY_WEB.bat
exit /b %errorlevel%

:git_missing
echo.
echo Git is not installed or Windows cannot find it.
echo Aivy was not changed.
echo.
echo Install Git for Windows once, then double-click this file again.
echo Opening the official Git for Windows download page...
start "" "https://git-scm.com/download/win"
pause
exit /b 1

:folder_problem
echo.
echo Aivy could not find a safe empty installation folder.
echo Nothing was deleted.
pause
exit /b 1

:failed
echo.
echo Aivy installation or startup failed.
echo Nothing was force-deleted.
pause
exit /b 1
