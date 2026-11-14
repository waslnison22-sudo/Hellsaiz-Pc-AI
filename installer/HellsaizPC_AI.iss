#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{B70D1E04-91A6-4B1B-A46A-39C6F1B4A190}
AppName=Hellsaiz PC AI
AppVersion={#AppVersion}
AppPublisher=Hellsaiz
DefaultDirName={autopf}\Hellsaiz PC AI
DefaultGroupName=Hellsaiz PC AI
UninstallDisplayIcon={app}\HellsaizLauncher.exe
OutputDir=..\dist
OutputBaseFilename=HellsaizPC_AI_Setup
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
Uninstallable=yes
VersionInfoVersion={#AppVersion}
VersionInfoProductName=Hellsaiz PC AI
VersionInfoCompany=Hellsaiz

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные ярлыки:"

[Files]
Source: "..\dist\install\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Hellsaiz PC AI"; Filename: "{app}\HellsaizLauncher.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Hellsaiz PC AI"; Filename: "{app}\HellsaizLauncher.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\HellsaizLauncher.exe"; Description: "Запустить Hellsaiz PC AI"; Flags: postinstall nowait skipifsilent
