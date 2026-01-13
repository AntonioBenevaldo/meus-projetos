@echo off
setlocal enableextensions enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

REM ======== Confere EXE ========
if not exist "dist\SistemaNFE.exe" (
  echo [ERRO] Nao encontrei dist\SistemaNFE.exe
  echo Rode primeiro: build_exe_program_files.bat
  pause
  exit /b 1
)

REM ======== Encontra ISCC.exe (Inno Setup) ========
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto :found
set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" goto :found

for /f "delims=" %%i in ('where ISCC.exe 2^>nul') do (
  set "ISCC=%%i"
  goto :found
)

echo [ERRO] Inno Setup (ISCC.exe) nao encontrado.
echo Instale o Inno Setup 6 e tente novamente.
pause
exit /b 1

:found
echo Usando: %ISCC%
echo Compilando installer...
if not exist "output" mkdir "output"

"%ISCC%" "SistemaNFE_program_files.iss"
if errorlevel 1 (
  echo [ERRO] Falha ao compilar o instalador.
  pause
  exit /b 1
)

echo OK! Instalador gerado em:
echo   %cd%\output\SistemaNFE_Setup.exe
pause
