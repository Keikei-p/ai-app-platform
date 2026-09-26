@echo off
setlocal
cd /d "%~dp0"
call :find_python
if not defined PY goto :no_python

set "APP_VERSION=unknown"
if exist VERSION set /p APP_VERSION=<VERSION
echo AI App Platform v%APP_VERSION%
echo Running startup checks...
%PY% -m src.tools.preflight || goto :failed
%PY% -m unittest discover -s tests -q || goto :failed

echo Starting app...
%PY% -m src.main
goto :eof

:find_python
set "PY="
python -c "import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto :eof
py -3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=py -3"
goto :eof

:no_python
echo ERROR: Python 3.11 or newer was not found.
echo Run SETUP.bat first.
pause
exit /b 1

:failed
echo ERROR: A startup check failed.
echo Run DIAGNOSTICS.bat and send diagnostics.json if needed.
pause
exit /b 1
