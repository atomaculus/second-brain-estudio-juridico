@echo off
title PJN - Iniciar sesion y revision
echo ============================================================
echo   PJN - Iniciar sesion y correr la revision del dia
echo ============================================================
echo.
echo Se va a abrir una ventana del navegador con PJN.
echo Cuando aparezca, inicia sesion como siempre (tu usuario y
echo contrasena de PJN). No cierres esta ventana negra.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\scripts\run_pjn_assisted_review.ps1"
echo.
echo ============================================================
echo   Termino. Ya podes cerrar esta ventana.
echo ============================================================
pause
