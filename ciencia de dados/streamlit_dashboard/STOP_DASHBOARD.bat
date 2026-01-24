@echo off
chcp 65001 >nul

set PORT=8510

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do set PID=%%a

if not defined PID (
  echo Nenhum processo usando a porta %PORT%.
  pause
  exit /b 0
)

echo Finalizando processo PID %PID% (porta %PORT%)...
taskkill /PID %PID% /F
pause