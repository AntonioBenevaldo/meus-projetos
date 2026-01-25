@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

set PORT=8510

echo Procurando processo na porta %PORT% ...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%PORT% ^| findstr LISTENING') do (
  set PID=%%a
  echo Encerrando PID !PID! ...
  taskkill /PID !PID! /F >nul 2>&1
)

echo.
echo Finalizado. Se estava rodando, foi encerrado.
pause