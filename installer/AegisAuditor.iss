#define MyAppName "Aegis Auditor"
#define MyAppVersion "1.1.5"
#define MyAppPublisher "Aegis Auditor Project"
#define MyAppExeName "AegisAuditor.exe"

[Setup]
AppId={{D9AC7206-37D1-49EF-9B84-A4D7BD694841}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Aegis Auditor
DefaultGroupName=Aegis Auditor
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=AegisAuditor-Setup
SetupIconFile=..\assets\aegis-auditor.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\LICENSE

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\dist\AegisAuditor.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\NOTICE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Aegis Auditor"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Aegis Auditor"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Aegis Auditor"; Flags: nowait postinstall skipifsilent
