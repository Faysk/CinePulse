@echo off
setlocal EnableExtensions
call "%~dp0installer\CinePulse-Environment.cmd"
set "CINEPULSE_PORTABLE=1"
set "CINEPULSE_INSTALL_MODE=portable-self-contained"
title CinePulse - Instalacao completa
color 0B

echo.
echo ================================================================
echo   CinePulse - instalacao dos componentes locais
echo ================================================================
echo.
echo Tudo sera instalado dentro de:
echo   %CINEPULSE_ROOT%
echo.
echo Runtime:     %CINEPULSE_ROOT%\.runtime
echo Componentes:%CINEPULSE_COMPONENTS_DIR%
echo Dados:       %CINEPULSE_DATA_DIR%
echo Cache:       %CINEPULSE_CACHE_DIR%
echo Temporarios: %CINEPULSE_TEMP_DIR%
echo.

set "CINEPULSE_POWERSHELL="
if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" set "CINEPULSE_POWERSHELL=%ProgramFiles%\PowerShell\7\pwsh.exe"
if not defined CINEPULSE_POWERSHELL for /f "delims=" %%P in ('where pwsh.exe 2^>nul') do if not defined CINEPULSE_POWERSHELL set "CINEPULSE_POWERSHELL=%%P"
if not defined CINEPULSE_POWERSHELL set "CINEPULSE_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

echo PowerShell selecionado: %CINEPULSE_POWERSHELL%
echo Log permanente: %CINEPULSE_DATA_DIR%\logs\installer.log
echo.

"%CINEPULSE_POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Start-CinePulse.ps1" -InstallOnly
set "CINEPULSE_EXIT=%ERRORLEVEL%"

echo.
if "%CINEPULSE_EXIT%"=="0" (
    color 0A
    echo ================================================================
    echo   INSTALACAO CONCLUIDA COM SUCESSO
    echo ================================================================
    echo O CinePulse e seus runtimes estao isolados em:
    echo   %CINEPULSE_ROOT%
) else (
    color 0C
    echo ================================================================
    echo   A INSTALACAO NAO FOI CONCLUIDA
    echo ================================================================
    echo Codigo do erro: %CINEPULSE_EXIT%
    echo Consulte: %CINEPULSE_DATA_DIR%\logs\installer.log
)
echo.
pause
exit /b %CINEPULSE_EXIT%
