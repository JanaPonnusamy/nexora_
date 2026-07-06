; ============================================================================
;  UniNex HO - Inno Setup project
;  Produces release\HO_Setup.exe: a single installer bundling HO_Backend.exe,
;  the frontend build, NEXORA_PLATFORM.bak, configuration templates, the
;  deployment helper (HO_Deploy.exe) and the standalone uninstaller.
;
;  Compiled by build.bat (PyInstaller first, then ISCC on this script).
;  Source paths are relative to this .iss file (installer\).
; ============================================================================

#define AppName        "UniNex HO"
#define AppVersion     "1.0.0"
#define AppPublisher   "UniNex"
#define ServiceName    "UniNexHO"

[Setup]
AppId={{B7B6F4B2-2C2E-4E2C-9C7B-0A1B2C3D4E5F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\UniNex\HO
DefaultGroupName=UniNex HO
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=HO_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\ho_setup\LICENSE.txt
SetupLogging=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\HO_Backend.exe

[Dirs]
Name: "{app}\logs"
Name: "{app}\uploads"
Name: "{app}\config"

[Files]
; --- backend service host (PyInstaller onedir) ---
Source: "..\dist\HO_Backend\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; --- production frontend build ---
Source: "..\frontend\dist\*"; DestDir: "{app}\frontend"; Flags: ignoreversion recursesubdirs createallsubdirs
; --- deployment helper: installed AND extractable during the wizard (dontcopy) ---
Source: "..\dist\HO_Deploy.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\HO_Deploy.exe"; Flags: dontcopy
; --- standalone uninstaller ---
Source: "..\dist\HO_Uninstall.exe"; DestDir: "{app}"; Flags: ignoreversion
; --- configuration template + license ---
Source: "..\ho_setup\templates\ho.env.template"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "..\ho_setup\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Open UniNex HO"; Filename: "{app}\frontend\index.html"
Name: "{group}\Uninstall UniNex HO"; Filename: "{uninstallexe}"

[UninstallRun]
; Stop + remove the Windows service before Inno deletes the files (which would
; otherwise be locked by the running service). Files are removed by Inno.
Filename: "{app}\HO_Deploy.exe"; Parameters: "uninstall --install-dir ""{app}"" --keep-files"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveUniNexHOService"

[Code]
{ Force a hard, non-zero process exit. RaiseException/Abort in ssPostInstall are
  NON-fatal in Inno (Setup still reports success), so a failed mandatory step
  must terminate the process itself. }
procedure ExitProcess(uExitCode: Cardinal);
  external 'ExitProcess@kernel32.dll stdcall';

var
  PageAuth: TInputOptionWizardPage;
  PageSql: TInputQueryWizardPage;
  PageWeb: TInputQueryWizardPage;
  TestButton: TNewButton;

function AuthIsWindows(): Boolean;
begin
  Result := PageAuth.SelectedValueIndex = 1;
end;

function TailFile(const FileName: String): String;
var
  Lines: TArrayOfString;
  i, startIdx: Integer;
begin
  Result := '';
  if LoadStringsFromFile(FileName, Lines) then
  begin
    startIdx := 0;
    if GetArrayLength(Lines) > 25 then
      startIdx := GetArrayLength(Lines) - 25;
    for i := startIdx to GetArrayLength(Lines) - 1 do
      Result := Result + Lines[i] + #13#10;
  end;
end;

procedure WriteParams(FileName: String; Replace: String);
var
  S: TStringList;
  Auth: String;
begin
  if AuthIsWindows() then Auth := 'WINDOWS' else Auth := 'SQL';
  S := TStringList.Create();
  try
    S.Add('[deploy]');
    S.Add('server=' + PageSql.Values[0]);
    S.Add('database=' + PageSql.Values[1]);
    S.Add('auth_mode=' + Auth);
    S.Add('username=' + PageSql.Values[2]);
    S.Add('password=' + PageSql.Values[3]);
    S.Add('install_dir=' + ExpandConstant('{app}'));
    S.Add('public_host=' + PageWeb.Values[0]);
    S.Add('port=' + PageWeb.Values[1]);
    S.Add('replace=' + Replace);
    S.SaveToFile(FileName);
  finally
    S.Free();
  end;
end;

procedure TestConnectionClick(Sender: TObject);
var
  Params: String;
  ResultCode: Integer;
begin
  ExtractTemporaryFile('HO_Deploy.exe');
  Params := ExpandConstant('{tmp}\ho_test.ini');
  WriteParams(Params, 'false');
  if Exec(ExpandConstant('{tmp}\HO_Deploy.exe'),
          'test-sql --params "' + Params + '"', '',
          SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if ResultCode = 0 then
      MsgBox('SQL connection successful.', mbInformation, MB_OK)
    else
      MsgBox('SQL connection FAILED.' + #13#10 +
             'Check the instance name, credentials and that SQL Server is running.',
             mbError, MB_OK);
  end
  else
    MsgBox('Could not run HO_Deploy.exe.', mbError, MB_OK);
end;

procedure InitializeWizard();
begin
  PageAuth := CreateInputOptionPage(wpSelectDir,
    'SQL Server Authentication',
    'How should HO connect to SQL Server?',
    'Choose the authentication method, then click Next.', True, False);
  PageAuth.Add('SQL Server Authentication (username and password)');
  PageAuth.Add('Windows Authentication (trusted connection)');
  PageAuth.SelectedValueIndex := 0;

  PageSql := CreateInputQueryPage(PageAuth.ID,
    'SQL Server Configuration',
    'Enter the SQL Server connection details.',
    'These are used to restore and connect the HO database, then click Test Connection.');
  PageSql.Add('SQL Server instance (e.g. localhost or .\SQLEXPRESS):', False);
  PageSql.Add('Database name:', False);
  PageSql.Add('Username:', False);
  PageSql.Add('Password:', True);
  PageSql.Values[0] := 'localhost';
  PageSql.Values[1] := 'NEXORA_PLATFORM';
  PageSql.Values[2] := 'sa';

  TestButton := TNewButton.Create(WizardForm);
  TestButton.Parent := PageSql.Surface;
  TestButton.Caption := 'Test Connection';
  TestButton.Width := ScaleX(130);
  TestButton.Height := ScaleY(25);
  TestButton.Left := 0;
  TestButton.Top := PageSql.Edits[3].Top + ScaleY(36);
  TestButton.OnClick := @TestConnectionClick;

  PageWeb := CreateInputQueryPage(PageSql.ID,
    'Web Server Settings',
    'How will browsers reach this HO server?',
    'The API and web application are served on this address and port.');
  PageWeb.Add('Server address (hostname or IP):', False);
  PageWeb.Add('Port:', False);
  PageWeb.Values[0] := ExpandConstant('{computername}');
  PageWeb.Values[1] := '8000';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = PageSql.ID then
  begin
    if Trim(PageSql.Values[0]) = '' then
    begin
      MsgBox('Please enter the SQL Server instance.', mbError, MB_OK);
      Result := False; Exit;
    end;
    if Trim(PageSql.Values[1]) = '' then
    begin
      MsgBox('Please enter the database name.', mbError, MB_OK);
      Result := False; Exit;
    end;
    if (not AuthIsWindows()) and (Trim(PageSql.Values[2]) = '') then
    begin
      MsgBox('Please enter the SQL username (or choose Windows Authentication).',
             mbError, MB_OK);
      Result := False; Exit;
    end;
  end
  else if CurPageID = PageWeb.ID then
  begin
    if Trim(PageWeb.Values[1]) = '' then
    begin
      MsgBox('Please enter the port (e.g. 8000).', mbError, MB_OK);
      Result := False; Exit;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  DeployExe, Params, AppDir, LogFile, ErrText: String;
  RC, Ignore: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    AppDir    := ExpandConstant('{app}');
    DeployExe := AppDir + '\HO_Deploy.exe';
    Params    := ExpandConstant('{tmp}\ho_deploy.ini');
    LogFile   := AppDir + '\logs\deploy.log';

    { App-only build: configure -> install service -> start -> verify API.
      No database restore is performed; the DB is created manually. }
    WriteParams(Params, 'false');
    WizardForm.StatusLabel.Caption := 'Configuring HO and installing the service...';

    if not Exec(DeployExe, 'deploy --params "' + Params + '" --skip-db', '',
                SW_SHOW, ewWaitUntilTerminated, RC) then
      RC := -1;

    { Mandatory final gate: the Windows service MUST exist and be running.
      Success is reported ONLY if this passes. }
    if RC = 0 then
      if not Exec(DeployExe, 'verify-service --params "' + Params + '"', '',
                  SW_HIDE, ewWaitUntilTerminated, RC) then
        RC := -1;

    DeleteFile(Params);

    if RC <> 0 then
    begin
      ErrText := TailFile(LogFile);
      if ErrText = '' then
        ErrText := '(no deploy log was produced - the helper could not run, '
                 + 'or Administrator rights were missing).';
      MsgBox('HO installation FAILED.' + #13#10
           + 'The Windows service "UniNexHO" was NOT installed, so Setup cannot '
           + 'complete.' + #13#10#13#10
           + 'Actual error:' + #13#10 + ErrText + #13#10
           + 'The installation will now be rolled back. Re-run as Administrator.',
             mbCriticalError, MB_OK);

      { Roll back: remove any partially created service, then delete the files. }
      Exec(DeployExe, 'uninstall --install-dir "' + AppDir + '" --keep-files',
           '', SW_HIDE, ewWaitUntilTerminated, Ignore);
      DelTree(AppDir, True, True, True);

      { ssPostInstall RaiseException/Abort are non-fatal in Inno, so terminate
        the process with a non-zero exit code: Setup can never report success. }
      ExitProcess(1);
    end;
  end;
end;
