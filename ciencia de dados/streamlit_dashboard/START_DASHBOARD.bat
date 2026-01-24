@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PORT=8510

if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  python -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo Instalando dependencias...
python -m pip install --upgrade pip >nul
python -m pip install streamlit pandas numpy plotly openpyxl >nul

echo Abrindo Dashboard Power BI Premium v2...
start "" http://127.0.0.1:%PORT%

streamlit run aypp.py --server.port %PORT% --server.address 127.0.0.1
pause