@echo off
setlocal
cd /d "%~dp0"
echo AI App Platform setup check
python -c "import sys;print(sys.version);raise SystemExit(0 if sys.version_info>=(3,11) else 1)" 2>nul
if not errorlevel 1 goto :ok
py -3 -c "import sys;print(sys.version);raise SystemExit(0 if sys.version_info>=(3,11) else 1)" 2>nul
if not errorlevel 1 goto :ok

echo Python 3.11 or newer is required.
where winget >nul 2>nul || goto :manual
choice /M "Install Python 3.12 with winget"
if errorlevel 2 goto :done
winget install -e --id Python.Python.3.12
goto :done

:manual
echo Install Python 3.11+ from python.org and run START.bat again.
goto :done

:ok
echo Python is ready.
echo Next: START.bat
:done
pause
