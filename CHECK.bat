@echo off
setlocal
cd /d "%~dp0"
call :find_python
if not defined PY goto :no_python

echo [1/11] Compile
%PY% -m compileall -q src tests || goto :failed
echo [2/11] Security self-check
%PY% -m src.tools.security_selfcheck || goto :failed
echo [3/11] Preflight
%PY% -m src.tools.preflight || goto :failed
echo [4/11] Unit tests
%PY% -m unittest discover -s tests -v || goto :failed
echo [5/11] Persistence acceptance
%PY% -m src.tools.acceptance_test || goto :failed
echo [6/11] GUI editing acceptance
%PY% -m src.tools.acceptance_test --gui || goto :failed
echo [7/11] Update engine acceptance
%PY% -m src.tools.update_acceptance_test || goto :failed
echo [8/11] Remote LAN acceptance
%PY% -m src.tools.remote_acceptance_test || goto :failed
echo [9/11] Remote GUI acceptance
%PY% -m src.tools.remote_gui_acceptance_test || goto :failed
echo [10/11] Chat composer acceptance
%PY% -m src.tools.chat_gui_acceptance_test || goto :failed
echo [11/11] Production smoke test
%PY% -m src.tools.smoke_test || goto :failed

echo.
echo ALL CHECKS PASSED
pause
exit /b 0

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
pause
exit /b 1

:failed
echo.
echo CHECK FAILED. Creating diagnostics...
%PY% -m src.tools.diagnostics_cli
pause
exit /b 1
