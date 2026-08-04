@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Start-CinePulse.ps1" %*
exit /b %errorlevel%

