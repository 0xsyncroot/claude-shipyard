@echo off
rem claude-shipyard: CHECK ONLY - changes nothing.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" -Check %*
set RC=%ERRORLEVEL%
echo.
echo Log: "%~dp0install-log.txt"
pause
exit /b %RC%
