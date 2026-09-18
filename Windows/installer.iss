; Fixelect for Windows - installer (Inno Setup 7)
;
; CI passes /DMyAppVersion=x.y.z from the release tag, /DSourceDir for an alternate
; build folder, and /DSIGN (with /Sfixsign=...) when a code-signing certificate is
; available. Windows only shows "Bositxon Erkinxonov" as the verified publisher
; when the files are signed with a certificate issued in that name.

#define MyAppName "Fixelect"
#ifndef MyAppVersion
  #define MyAppVersion "1.1.4"
#endif
#ifndef SourceDir
  #define SourceDir "dist\Fixelect"
#endif
#define MyAppPublisher "Bositxon Erkinxonov"
#define MyAppCopyright "Copyright (C) 2026 Bositxon Erkinxonov"
#define MyAppURL "https://github.com/Bosithonn/fixelect"
#define MyAppExeName "Fixelect.exe"
#define Art "installer_art"

[Setup]
AppId={{D37E86D2-7F62-4C10-85A5-A656FEA2E338}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright={#MyAppCopyright}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
#ifndef PREVIEW
; Asks the user to close a running Fixelect first. /DPREVIEW (screenshots only) skips it.
AppMutex=Fixelect_SingleInstance_Mutex
#endif
UninstallDisplayName={#MyAppName}

; Per-user install: no administrator rights and no UAC prompt
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
; Show the branded Welcome page (Inno hides it by default); reinstalling into
; Fixelect's own folder is normal, so no "folder already exists" question.
DisableWelcomePage=no
DirExistsWarning=no
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

; Look: the app's dark palette (#0B0D12) and brand artwork, styled title bar, no bevels
WizardStyle=modern dark windows11 includetitlebar hidebevels
WizardBackColor=#0B0D12
WizardBackColorDynamicDark=#0B0D12
WizardImageBackColor=#0B0D12
WizardSmallImageBackColor=#0B0D12
WizardImageFile={#Art}\wizard_100.png,{#Art}\wizard_125.png,{#Art}\wizard_150.png,{#Art}\wizard_175.png,{#Art}\wizard_200.png,{#Art}\wizard_250.png
WizardSmallImageFile={#Art}\small_100.png,{#Art}\small_125.png,{#Art}\small_150.png,{#Art}\small_175.png,{#Art}\small_200.png,{#Art}\small_250.png
SetupIconFile=resources\app_icon.ico
UninstallDisplayIcon={app}\resources\app_icon.ico
LicenseFile=LICENSE.txt

; File properties of FixelectSetup.exe
VersionInfoVersion={#MyAppVersion}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoCopyright={#MyAppCopyright}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}

OutputDir=dist
OutputBaseFilename=FixelectSetup
#ifdef SIGN
SignTool=fixsign
SignedUninstaller=yes
#endif
Compression=lzma2/ultra64
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
SetupWindowTitle=Install %1
WelcomeLabel1=Welcome to [name]
WelcomeLabel2=Fix typos and polish your writing in any app with one shortcut.%n%nFixelect runs its AI model on this computer, so your text never leaves it. Installing takes about a minute; you will pick a model to download right after.
LicenseLabel3=Fixelect is free and open source under the MIT License. Please review it, then accept to continue.
WizardSelectTasks=Options
SelectTasksDesc=Choose how Fixelect starts.
SelectTasksLabel2=Pick what you would like, then click Next. You can change these later in Fixelect's settings.
WizardReady=Ready to install
ReadyLabel1=Fixelect will be installed for your Windows account. No administrator rights are needed.
ReadyLabel2a=Click Install to continue, or Back to change your options.
InstallingLabel=Installing [name]. This only takes a moment.
FinishedHeadingLabel=Fixelect is installed
FinishedLabelNoIcons=Select text in any app and double-tap Alt to fix it, or double-tap Ctrl to polish it.%n%nFixelect waits in the system tray.
FinishedLabel=Select text in any app and double-tap Alt to fix it, or double-tap Ctrl to polish it.%n%nFixelect waits in the system tray.
ClickFinish=Click Finish to close Setup.
RunEntryExec=Open %1 now

[Tasks]
Name: "startup"; Description: "Start Fixelect when I sign in to Windows"; GroupDescription: "Startup:"
Name: "desktopicon"; Description: "Add a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "resources\*.ico"; DestDir: "{app}\resources"; Flags: ignoreversion
Source: "resources\*.png"; DestDir: "{app}\resources"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\app_icon.ico"; Comment: "Fix and polish your writing in any app"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\resources\app_icon.ico"; Comment: "Fix and polish your writing in any app"; Tasks: desktopicon

[Registry]
; Start with Windows (the same entry Fixelect's own setting writes)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Fixelect"; ValueData: """{app}\{#MyAppExeName}"" --autostart"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
; In-app updates run the installer silently: start the new version afterwards.
Filename: "{app}\{#MyAppExeName}"; Parameters: "--silent"; Flags: nowait runasoriginaluser; Check: WizardSilent

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
      if MsgBox('Also remove the downloaded AI models (1-5 GB) from this computer?', mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(ModelsDir, True, True, True);
      end;
    end;
    RemoveDir(ExpandConstant('{localappdata}\Fixelect'));
  end;
end;
