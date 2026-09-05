#ifndef MyAppVersion
  #define MyAppVersion "0.1.0-dev"
#endif

#define MyAppName "LexPilot 律策"
#define MyAppExeName "LexPilot.exe"

[Setup]
AppId={{D34E236E-4F25-4A6F-B2E1-633D44624E4B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=LexPilot
DefaultDirName={localappdata}\Programs\LexPilot
DefaultGroupName=LexPilot 律策
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\release
OutputBaseFilename=LexPilot-Windows-x64-Setup-unsigned
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\..\LICENSE
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\..\dist\LexPilot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\LexPilot 律策"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\LexPilot 律策"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 LexPilot 律策"; Flags: nowait postinstall skipifsilent
