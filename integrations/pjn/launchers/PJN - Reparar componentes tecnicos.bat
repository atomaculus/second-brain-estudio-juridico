@echo off
title PJN - Reparar componentes tecnicos
echo ============================================================
echo   PJN - Reparar componentes tecnicos
echo ============================================================
echo.
echo Esto reinstala los componentes que PJN necesita para
echo funcionar. Puede tardar unos minutos. No cierres la ventana.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\scripts\setup_pjn_local.ps1"
echo.
echo ============================================================
echo   Termino. Ya podes cerrar esta ventana.
echo ============================================================
pause
