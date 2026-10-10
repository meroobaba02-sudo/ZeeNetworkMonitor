#define MyAppVersion "0.4.16"
[Setup]
AppId={{A677BBD3-90CC-4BCE-9DBA-A13F709DBB48}
AppName=Zee Network Monitor
AppVersion={#MyAppVersion}
AppPublisher=Zeeshan Rasool
DefaultDirName={localappdata}\Programs\ZeeNetworkMonitor
DefaultGroupName=Zee Network Monitor
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\release
OutputBaseFilename=ZeeNetworkMonitor-Setup-Windows-v0.4.16
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\ZeeNetworkMonitor.exe
CloseApplications=yes
[Files]
Source: "..\dist\ZeeNetworkMonitor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userdesktop}\Zee Network Monitor"; Filename: "{app}\ZeeNetworkMonitor.exe"; WorkingDir: "{app}"
Name: "{userprograms}\Zee Network Monitor\Zee Network Monitor"; Filename: "{app}\ZeeNetworkMonitor.exe"; WorkingDir: "{app}"
Name: "{userprograms}\Zee Network Monitor\Uninstall"; Filename: "{uninstallexe}"
[Run]
Filename: "{app}\ZeeNetworkMonitor.exe"; Description: "Launch Zee Network Monitor"; Flags: nowait postinstall skipifsilent
