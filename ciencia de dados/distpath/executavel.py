#define MyAppName "Dashboard Premium"
#define MyAppVersion "6.3"
#define MyAppPublisher "Benevaldo"
#define MyAppExeName "DashboardPremium.exe"
#define MyAppSourceDir "distpath\DashboardPremium"

[Setup]
; Gere um novo AppId (GUID) em: Tools > Generate GUID
AppId={{B7C0A9E7-6C98-4F24-9D2A-2AFB7D9F7A11}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}

DefaultDirName={pf}\DashboardPremium
DefaultGroupName={#MyAppName}

OutputBaseFilename=DashboardPremium_Setup
OutputDir=installer_output

Compression=lzma2
SolidCompression=yes

WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"
; Name: "quicklaunchicon"; Description: "Criar atalho na Barra de Inicialização Rápida"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName} agora"; Flags: nowait postinstall skipifsilent