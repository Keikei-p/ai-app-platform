@echo off
setlocal
cd /d "%~dp0"
call AIVY.bat web
exit /b %errorlevel%
