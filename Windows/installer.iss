; Script generated for Inno Setup 7
; Fixelect - Offline Windows Grammar & Polish Tool
; Installer Configuration

#define MyAppName "Fixelect"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Bositxon Erkinxonov"
#define MyAppURL "https://github.com/Bosithonn/fixelect"
#define MyAppExeName "Fixelect.exe"

[Setup]
; Basic Application Info
AppId={{D37E86D2-7F62-4C10-85A5-A656FEA2E338}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
AppMutex=Fixelect_SingleInstance_Mutex

; Installation Paths - Per-User (No Admin / UAC prompt required)
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Visuals & Branding
SetupIconFile=resources\app_icon.ico
UninstallDisplayIcon={app}\resources\app_icon.ico
LicenseFile=LICENSE.txt
WizardStyle=modern

; Output Binaries
OutputDir=dist
OutputBaseFilename=FixelectSetup
Compression=lzma2/ultra64
SolidCompression=yes

; Privileges - standard user install
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startup"; Description: "Launch Fixelect automatically when Windows boots"; GroupDescription: "Windows Integration:"

[Files]
Source: "dist\Fixelect\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "resources\*.ico"; DestDir: "{app}\resources"; Flags: ignoreversion
Source: "resources\*.png"; DestDir: "{app}\resources"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\app_icon.ico"; Comment: "Offline AI Grammar Correction & Executive Polish"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\app_icon.ico"; Comment: "Offline AI Grammar Correction & Executive Polish"; Tasks: desktopicon

[Registry]
; If startup task is selected, register in HKCU Run
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Fixelect"; ValueData: """{app}\{#MyAppExeName}"" --autostart"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\Fixelect\logs"
Type: files; Name: "{localappdata}\Fixelect\config.json"

[Code]
function InitializeUninstall(): Boolean;
var
  ErrorCode: Integer;
begin
  // Close Fixelect; its llama-server child exits with it (kill-on-close job object)
  Exec('taskkill.exe', '/f /im Fixelect.exe', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode);
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ModelsDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    ModelsDir := ExpandConstant('{localappdata}\Fixelect\models');
    if DirExists(ModelsDir) then
    begin
      if MsgBox('Do you also want to remove downloaded AI models from your computer to reclaim disk space?', mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(ModelsDir, True, True, True);
      end;
    end;
    RemoveDir(ExpandConstant('{localappdata}\Fixelect'));
  end;
end;
