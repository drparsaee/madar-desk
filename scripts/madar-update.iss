; Madar Desk safe-update installer. Compile with Inno Setup 6.
; Existing profile data is NEVER an installer-owned file.
; Override version/executable/output at build time for immutable releases.
#ifndef MadarVersion
#define MadarVersion "1.0.2"
#endif
#ifndef ExeFile
#define ExeFile "Madar-Desk-v1.0.2-Update-20261101.exe"
#endif
#ifndef EXE_SHA256
  #error Pass /DEXE_SHA256=<SHA256> to ISCC.
#endif
#ifdef QA
  #ifndef QA_ROOT
    #error QA_ROOT is required for isolated installer builds.
  #endif
  #ifdef RCOutputBase
  #define SetupBasename RCOutputBase
  #else
  #ifdef QAFRESH
  #define SetupBasename "Madar-Setup-v1.0.2-QA-Fresh-Fix1"
  #else
  #define SetupBasename "Madar-Setup-v1.0.2-QA-Fix1"
  #endif
  #endif
  #define AppGuid "{{7CBA8B02-1D55-480C-953D-00AE0DAB4104}"
#else
  #ifdef RCOutputBase
  #define SetupBasename RCOutputBase
  #else
  #define SetupBasename "Madar-Setup-v1.0.2-Update-20261101-Fix1"
  #endif
  #define AppGuid "{{92E35390-0AD9-4968-8F0B-64C0E9C51F7A}"
#endif

[Setup]
AppId={#AppGuid}
AppName=Madar Desk
AppVersion={#MadarVersion}
AppVerName=Madar Desk {#MadarVersion}
AppPublisher=Pack P.O.C.
AppPublisherURL=https://packpoc.com
AppSupportURL=https://packpoc.com
#ifdef QA
DefaultDirName={#QA_ROOT}\Programs\MadarDesk
#else
DefaultDirName={localappdata}\Programs\MadarDesk
#endif
DefaultGroupName=Madar Desk
PrivilegesRequired=lowest
UsePreviousAppDir=no
DisableDirPage=yes
DisableProgramGroupPage=yes
AllowNoIcons=yes
ShowLanguageDialog=no
MinVersion=10.0.17763
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no
RestartApplications=no
SetupLogging=yes
OutputDir=..\release
OutputBaseFilename={#SetupBasename}
SetupIconFile=..\assets\madar.ico
UninstallDisplayIcon={app}\versions\{#MadarVersion}\Madar-Desk.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
VersionInfoVersion={#MadarVersion}.0
VersionInfoCompany=Pack P.O.C.
VersionInfoDescription=Madar Desk offline update installer
#ifdef QA
Uninstallable=no
CreateUninstallRegKey=no
#endif

[Files]
; Immutable side-by-side binary. Old installed versions and all APPDATA remain.
Source: "..\release\{#ExeFile}"; DestDir: "{app}\versions\{#MadarVersion}"; DestName: "Madar-Desk.exe"; Flags: ignoreversion
Source: "Run-Madar.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "Madar-Upgrade-Preflight.ps1"; Flags: dontcopy
Source: "Madar-Activate-Version.ps1"; Flags: dontcopy
Source: "..\release\.madar-inno-prereq\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Flags: dontcopy

#ifndef QA
[Icons]
Name: "{userprograms}\مدار"; Filename: "{app}\Run-Madar.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\versions\{#MadarVersion}\Madar-Desk.exe"
Name: "{userdesktop}\مدار"; Filename: "{app}\Run-Madar.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\versions\{#MadarVersion}\Madar-Desk.exe"; Tasks: desktopicon
[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
#endif

[Code]
const
  WebViewClientKey = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  ExeSHA256 = '{#EXE_SHA256}';

function DataRoot(): String;
begin
#ifdef QA
  Result := '{#QA_ROOT}\Roaming\MadarDesk';
#else
  Result := ExpandConstant('{userappdata}\MadarDesk');
#endif
end;

function BackupRoot(): String;
begin
#ifdef QA
  Result := '{#QA_ROOT}\Snapshots';
#else
  Result := ExpandConstant('{localappdata}\MadarDesk-ReleaseBackups');
#endif
end;

function WebViewInstalled(): Boolean;
var
  Version: String;
begin
  Result := False;
  if RegQueryStringValue(HKCU, WebViewClientKey, 'pv', Version) or
     RegQueryStringValue(HKLM32, WebViewClientKey, 'pv', Version) or
     RegQueryStringValue(HKLM64, WebViewClientKey, 'pv', Version) then
    Result := (Version <> '') and (Version <> '0.0.0.0');
end;

function RunHiddenPowerShell(ScriptName, ExtraArgs: String; var ReturnCode: Integer): Boolean;
var
  Params: String;
begin
  ExtractTemporaryFile(ScriptName);
  Params := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
            ExpandConstant('{tmp}\') + ScriptName + '" ' + ExtraArgs;
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
                  Params, '', SW_HIDE, ewWaitUntilTerminated, ReturnCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
  Params: String;
begin
  Result := '';
  Params := '-DataRoot "' + DataRoot() + '" -BackupRoot "' + BackupRoot() +
            '" -TargetVersion "{#MadarVersion}"';
  if not RunHiddenPowerShell('Madar-Upgrade-Preflight.ps1', Params, Code) then begin
    Result := 'Could not run the pre-update safety check. Nothing was installed.';
    exit;
  end;
  if Code <> 0 then begin
    Result := 'Madar is running, data cannot be backed up, or the profile is unsafe.' +
              Chr(13) + Chr(10) + 'Close Madar and retry. The installed version is unchanged.';
    exit;
  end;
  if not WebViewInstalled() then begin
#ifdef QA
    { QA never installs a global prerequisite. }
    Result := '';
#else
    ExtractTemporaryFile('MicrosoftEdgeWebView2RuntimeInstallerX64.exe');
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe'),
                '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, Code) then begin
      Result := 'WebView2 Runtime setup could not be started.';
      exit;
    end;
    if (Code <> 0) or (not WebViewInstalled()) then begin
      Result := 'Microsoft WebView2 Runtime prerequisite could not be installed. Setup stopped.';
      exit;
    end;
#endif
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
  Args: String;
begin
  if CurStep <> ssPostInstall then exit;
  Args := '-InstallRoot "' + ExpandConstant('{app}') + '" -Version "{#MadarVersion}" ' +
          '-ExpectedSHA256 "' + ExeSHA256 + '"';
  if not RunHiddenPowerShell('Madar-Activate-Version.ps1', Args, Code) then
    RaiseException('Madar activation could not start. The previous version remains selected.');
  if Code <> 0 then
    RaiseException('Madar update could not activate. The previous version remains selected.');
end;
