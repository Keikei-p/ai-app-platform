@echo off
setlocal
cd /d "%~dp0"
set "PY="
python -c "import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY (
  py -3 -c "import sys;raise SystemExit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  echo ERROR: Python 3.11 or newer was not found.
  pause
  exit /b 1
)
%PY% -m src.tools.diagnostics_cli
pause
