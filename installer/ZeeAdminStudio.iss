#define MyAppVersion "0.4.15"
[Setup]
AppId={{5D36ECA3-A7F2-422A-9D3D-3BC38B5AD19D}
AppName=Zee Admin Studio
AppVersion={#MyAppVersion}
AppPublisher=Zeeshan Rasool
DefaultDirName={localappdata}\Programs\ZeeAdminStudio
DefaultGroupName=Zee Admin Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=ZeeAdminStudio-Setup-Windows-v0.4.15
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ZeeAdminStudio.exe
CloseApplications=yes
[Files]
Source: "..\dist\ZeeAdminStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userdesktop}\Zee Admin Studio"; Filename: "{app}\ZeeAdminStudio.exe"; WorkingDir: "{app}"
Name: "{userprograms}\Zee Admin Studio\Zee Admin Studio"; Filename: "{app}\ZeeAdminStudio.exe"; WorkingDir: "{app}"
Name: "{userprograms}\Zee Admin Studio\Uninstall"; Filename: "{uninstallexe}"
[Run]
Filename: "{app}\ZeeAdminStudio.exe"; Description: "Launch Zee Admin Studio"; Flags: nowait postinstall skipifsilent
