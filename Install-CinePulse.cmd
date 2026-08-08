@echo off
setlocal EnableExtensions
set "CUDA_DEVICE_ORDER=PCI_BUS_ID"
set "CUDA_VISIBLE_DEVICES=0"
set "CINEPULSE_PREFER_DEDICATED_GPU=1"
title CinePulse - Instalacao completa
color 0B

echo.
echo ================================================================
echo   CinePulse - instalacao dos componentes locais
echo ================================================================
echo.
echo Esta janela mostra tudo o que esta sendo instalado.
echo Ela permanecera aberta para informar o resultado final.
echo.

set "CINEPULSE_POWERSHELL="
if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" set "CINEPULSE_POWERSHELL=%ProgramFiles%\PowerShell\7\pwsh.exe"
if not defined CINEPULSE_POWERSHELL for /f "delims=" %%P in ('where pwsh.exe 2^>nul') do if not defined CINEPULSE_POWERSHELL set "CINEPULSE_POWERSHELL=%%P"
if not defined CINEPULSE_POWERSHELL set "CINEPULSE_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

echo PowerShell selecionado: %CINEPULSE_POWERSHELL%
echo Log permanente: %~dp0data\logs\installer.log
echo.

"%CINEPULSE_POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\Start-CinePulse.ps1" -InstallOnly
set "CINEPULSE_EXIT=%ERRORLEVEL%"

echo.
if "%CINEPULSE_EXIT%"=="0" (
    color 0A
    echo ================================================================
    echo   INSTALACAO CONCLUIDA COM SUCESSO
    echo ================================================================
    echo O atalho do CinePulse esta disponivel na Area de Trabalho.
) else (
    color 0C
    echo ================================================================
    echo   A INSTALACAO NAO FOI CONCLUIDA
    echo ================================================================
    echo Codigo do erro: %CINEPULSE_EXIT%
    echo Consulte: %~dp0data\logs\installer.log
)
echo.
pause
exit /b %CINEPULSE_EXIT%
