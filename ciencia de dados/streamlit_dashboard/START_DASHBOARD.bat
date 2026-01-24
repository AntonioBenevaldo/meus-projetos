@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PORT=8510

REM cria venv se não existir
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  python -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo Instalando dependencias (se faltar)...
python -m pip install --upgrade pip >nul
python -m pip install streamlit pandas numpy plotly openpyxl xlsxwriter >nul
echo Abrindo navegador...
start "" "http://127.0.0.1:%PORT%"

echo Iniciando Streamlit na porta %PORT%...
python -m streamlit run app.py --server.port %PORT% --server.address 127.0.0.1

pause