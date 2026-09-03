@echo off
setlocal
title PJN - Ver ultimo resultado
set "PJN_RESULT_HTML=%~dp0..\..\..\09-reviews\pjn\ULTIMO-RESULTADO.html"
set "PJN_RESULT_MD=%~dp0..\..\..\09-reviews\pjn\ULTIMA-CORRIDA.md"

if exist "%PJN_RESULT_HTML%" (
  start "" "%PJN_RESULT_HTML%"
  exit /b 0
)

if exist "%PJN_RESULT_MD%" (
  start "" "%PJN_RESULT_MD%"
  exit /b 0
)

echo No se encontro un resultado PJN para mostrar.
echo Primero debe completarse al menos una revision.
echo.
pause
exit /b 1
