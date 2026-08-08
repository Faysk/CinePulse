@echo off
setlocal EnableExtensions
set "CUDA_DEVICE_ORDER=PCI_BUS_ID"
set "CUDA_VISIBLE_DEVICES=0"
set "CINEPULSE_PREFER_DEDICATED_GPU=1"
set "CINEPULSE_POWERSHELL="
if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" set "CINEPULSE_POWERSHELL=%ProgramFiles%\PowerShell\7\pwsh.exe"
if not defined CINEPULSE_POWERSHELL for /f "delims=" %%P in ('where pwsh.exe 2^>nul') do if not defined CINEPULSE_POWERSHELL set "CINEPULSE_POWERSHELL=%%P"
if not defined CINEPULSE_POWERSHELL set "CINEPULSE_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
"%CINEPULSE_POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Start-CinePulse.ps1" %*
exit /b %errorlevel%
