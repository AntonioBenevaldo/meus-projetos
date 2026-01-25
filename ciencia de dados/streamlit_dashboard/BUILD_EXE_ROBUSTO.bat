@echo off
chcp 65001 >nul
setlocal

REM =====================================
REM Build EXE (PyInstaller) - FIX v3
REM =====================================

cd /d "%~dp0"

REM ---------- AJUSTE AQUI ----------
set ENTRY=powerbi.py
REM ----------------------------------

echo.
echo [CHECK] Verificando arquivo de entrada...
if not exist "%ENTRY%" (
  echo [ERRO] Nao encontrei "%ENTRY%" nesta pasta.
  echo.
  echo DICA 1: se seu arquivo se chama "power_bi.py", entao:
  echo        - renomeie para powerbi.py
  echo        OU
  echo        - edite este .bat e mude ENTRY=power_bi.py
  echo.
  echo DICA 2: ative "Extensoes de nome de arquivo" no Windows Explorer.
  pause
  exit /b 1
)

echo.
echo [CHECK] Verificando arquivo SPEC...
if not exist "DashboardPowerBI.spec" (
  echo [ERRO] Nao encontrei DashboardPowerBI.spec
  pause
  exit /b 1
)

echo.
echo [1/5] Criando/ativando venv...
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
)
call ".venv\Scripts\activate.bat"

echo.
echo [2/5] Instalando dependencias + hooks...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo [3/5] Limpando build antigo...
if exist "build" rmdir /s /q "build"
if exist "dist"  rmdir /s /q "dist"

echo.
echo [4/5] Gerando executavel (onedir) usando SPEC...
echo (Se seu arquivo nao for powerbi.py, edite o SPEC tambem!)
pyinstaller --noconfirm --clean DashboardPowerBI.spec

echo.
echo [5/5] Validacao...
if exist "dist\DashboardPowerBI\DashboardPowerBI.exe" (
  echo OK: dist\DashboardPowerBI\DashboardPowerBI.exe
) else (
  echo [ERRO] Nao encontrei o executavel gerado.
  echo Abra este arquivo e veja a mensagem acima.
)

echo.
pause
