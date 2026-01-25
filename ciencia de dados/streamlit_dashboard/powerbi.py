from pathlib import Path
import zipfile

base = Path("/mnt/data/dashboard_build_pack_v3_fix")
base.mkdir(parents=True, exist_ok=True)

# requirements
(base / "requirements.txt").write_text(
"""PySide6>=6.5
pandas>=2.0
openpyxl>=3.1
pyinstaller>=6.0
pyinstaller-hooks-contrib>=2024.0
""", encoding="utf-8"
)

# Spec template referencing ENTRY variable placeholder
(base / "DashboardPowerBI.spec").write_text(
r"""# -*- mode: python ; coding: utf-8 -*-
# Se o seu arquivo NÃO se chama powerbi.py, mude aqui: ["powerbi.py"] -> ["SEU_ARQUIVO.py"]

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

datas, binaries, hiddenimports = [], [], []

# Coleta tudo do PySide6 e Shiboken6 (plugins Qt + dlls)
for pkg in ("PySide6", "shiboken6"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Garante módulos do QtCharts
hiddenimports += collect_submodules("PySide6.QtCharts")
hiddenimports = list(sorted(set(hiddenimports)))

a = Analysis(
    ["powerbi.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DashboardPowerBI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="DashboardPowerBI",
)
""", encoding="utf-8"
)

# Build bat FIXED: no deletion of spec; checks for file names
(base / "BUILD_EXE_ROBUSTO.bat").write_text(
r"""@echo off
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
""", encoding="utf-8"
)

(base / "DIAG_RUN.bat").write_text(
r"""@echo off
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
""", encoding="utf-8"
)

(base / "installer_inno_v2.iss").write_text(
r""";---------------------------------------------
; Installer (Setup.exe) - Inno Setup (v2 robusto)
;---------------------------------------------
#define AppName "Dashboard PowerBI"
#define AppVersion "1.0.0"
#define AppPublisher "Dashboard Analytics"
#define AppExeName "DashboardPowerBI.exe"

[Setup]
AppId={{D0D17C7E-8E0B-4DBF-8A0F-8E1E5D49C5B7}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=installer_out
OutputBaseFilename=Setup_{#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#AppExeName}
SetupLogging=yes

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
Source: "dist\DashboardPowerBI\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent
""", encoding="utf-8"
)

(base / "LEIA_PRIMEIRO.txt").write_text(
"""CORREÇÃO IMPORTANTE (v3)

No seu print, o arquivo aparece como "power_bi" (provavelmente power_bi.py).
O build usa por padrão: powerbi.py

FAÇA UM DESTES 2:
A) RENOMEAR o arquivo para: powerbi.py
B) OU editar BUILD_EXE_ROBUSTO.bat e mudar: ENTRY=power_bi.py
   e também editar DashboardPowerBI.spec:
   trocar ["powerbi.py"] por ["power_bi.py"]

Depois rode:
1) BUILD_EXE_ROBUSTO.bat
2) DIAG_RUN.bat (teste)
3) installer_inno_v2.iss (Compile no Inno Setup)
""", encoding="utf-8"
)

zip_path = Path("/mnt/data/dashboard_build_pack_v3_fix.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for p in base.rglob("*"):
        z.write(p, p.relative_to(base))
zip_path