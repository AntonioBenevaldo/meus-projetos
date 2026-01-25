@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==================================================
echo DIAGNOSTICO - Rodar EXE e capturar erro no console
echo ==================================================
echo.

if not exist "dist\DashboardPowerBI\DashboardPowerBI.exe" (
  echo [ERRO] Nao achei dist\DashboardPowerBI\DashboardPowerBI.exe
  echo Primeiro rode BUILD_EXE_ROBUSTO.bat
  pause
  exit /b 1
)

"dist\DashboardPowerBI\DashboardPowerBI.exe"

echo.
echo Fim do diagnostico.
pause
