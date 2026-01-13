@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERRO] Nao encontrei o venv ".venv". Crie com: python -m venv .venv
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"

echo.
echo Iniciando FastAPI em http://127.0.0.1:8000
echo Para parar: CTRL + C
echo.

uvicorn main:app --reload --host 127.0.0.1 --port 8000

pause