@echo off
setlocal enableextensions enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

REM ======== Config ========
set "APP_NAME=SistemaNFE"
set "ENTRY=sistema_gui_principal_instalavel.py"

REM ======== Escolhe Python (prioriza .venv) ========
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"

REM NOTE: Se seu venv tiver outro nome, ajuste acima.

echo [1/3] Instalando/atualizando PyInstaller...
"%PY%" -m pip install -U pyinstaller
if errorlevel 1 (
  echo [ERRO] Falha ao instalar PyInstaller. Verifique seu Python/pip.
  pause
  exit /b 1
)

echo [2/3] Gerando EXE...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

"%PY%" -m PyInstaller --noconfirm --clean --windowed --onefile --name "%APP_NAME%" "%ENTRY%"
if errorlevel 1 (
  echo [ERRO] PyInstaller falhou.
  pause
  exit /b 1
)

echo [3/3] OK! EXE gerado em:
echo   %cd%\dist\%APP_NAME%.exe
pause
