@echo off
setlocal
title PJN - Instalar en esta PC
echo ============================================================
echo   PJN - Instalar el revisador en esta PC
echo ============================================================
echo.
echo Este instalador prepara componentes locales y crea accesos
echo directos. No copia claves ni activa tareas programadas.
echo Puede descargar Python, Node, Playwright y Chromium.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_pjn_workstation.ps1"
set "PJN_INSTALL_EXIT=%ERRORLEVEL%"
echo.
if not "%PJN_INSTALL_EXIT%"=="0" (
  echo La instalacion no termino correctamente. Revisa el mensaje anterior.
) else (
  echo Instalacion terminada correctamente.
)
echo.
pause
exit /b %PJN_INSTALL_EXIT%
