@echo off
setlocal EnableExtensions
call "%~dp0installer\CinePulse-Environment.cmd"
set "CINEPULSE_PORTABLE=0"
set "CINEPULSE_INSTALL_MODE=installed-self-contained"
set "CINEPULSE_POWERSHELL="
if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" set "CINEPULSE_POWERSHELL=%ProgramFiles%\PowerShell\7\pwsh.exe"
if not defined CINEPULSE_POWERSHELL for /f "delims=" %%P in ('where pwsh.exe 2^>nul') do if not defined CINEPULSE_POWERSHELL set "CINEPULSE_POWERSHELL=%%P"
if not defined CINEPULSE_POWERSHELL set "CINEPULSE_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

echo.
echo ================================================================
echo   CinePulse - preparando ambiente isolado
 echo ================================================================
echo Pasta escolhida: %CINEPULSE_ROOT%
echo Python/runtime: %CINEPULSE_ROOT%\.runtime
echo Componentes:    %CINEPULSE_COMPONENTS_DIR%
echo Dados:          %CINEPULSE_DATA_DIR%
echo Cache:          %CINEPULSE_CACHE_DIR%
echo Temporarios:    %CINEPULSE_TEMP_DIR%
echo.

"%CINEPULSE_POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Start-CinePulse.ps1" -NonPortable -InstallOnly %*
exit /b %errorlevel%
