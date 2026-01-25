@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PORT=8510
set APP=app_pbi_premium_v3_safe.py

REM Mata processo preso na porta
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do (
  taskkill /PID %%a /F >nul 2>&1
)

REM Cria venv se não existir
if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Criando ambiente virtual .venv...
  python -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo [INFO] Instalando dependencias (se faltar)...
python -m pip install -U pip >nul
python -m pip install -q streamlit pandas numpy plotly openpyxl xlsxwriter >nul

echo.
echo [OK] Abrindo no navegador...
start "" http://127.0.0.1:%PORT%

echo [OK] Iniciando Streamlit...
streamlit run "%APP%" --server.port %PORT% --server.address 127.0.0.1

pause