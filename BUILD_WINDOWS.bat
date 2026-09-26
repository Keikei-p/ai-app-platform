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

echo Running checks before build...
%PY% -m compileall -q src tests || goto :failed
%PY% -m src.tools.security_selfcheck || goto :failed
%PY% -m unittest discover -s tests -q || goto :failed
%PY% -m src.tools.acceptance_test || goto :failed
%PY% -m src.tools.acceptance_test --gui || goto :failed
%PY% -m src.tools.smoke_test || goto :failed

echo Checking PyInstaller...
%PY% -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo Installing PyInstaller 6.22.3...
  %PY% -m pip install "pyinstaller==6.22.3" || goto :failed
)

%PY% -m PyInstaller --noconfirm --clean --windowed --name "AI-App-Platform" --paths . src/main.py || goto :failed

echo.
echo BUILD PASSED
echo EXE: dist\AI-App-Platform\AI-App-Platform.exe
echo User data: %%LOCALAPPDATA%%\AI-App-Platform
pause
exit /b 0

:failed
echo.
echo BUILD FAILED
%PY% -m src.tools.diagnostics_cli
pause
exit /b 1
