@echo off
rem claude-shipyard: install / update the skills for Claude Code on Windows. Safe to run again.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set RC=%ERRORLEVEL%
echo.
echo Log: "%~dp0install-log.txt"
pause
exit /b %RC%
