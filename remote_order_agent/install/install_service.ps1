# Installs NMVSyncAgent as a Windows service. Run in an elevated PowerShell:
#   powershell -ExecutionPolicy Bypass -File install_service.ps1
# Idempotent: re-running upgrades the binaries and keeps the existing config/secrets.
param(
    [string]$InstallDir = 'D:\NMVSyncAgent',
    [string]$SqlInstance = 'DESKTOP-2\SQLEXPRESSORDER',
    [string]$Database = 'OrderNMC',
    [switch]$NoStart
)
$ErrorActionPreference = 'Stop'
$pkg  = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)   # D:\VBDOTNET\NMVSyncAgent
$svc  = 'NMVSyncAgent'
$acct = "NT SERVICE\$svc"
$data = Join-Path $env:ProgramData 'NMVSyncAgent'
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run as Administrator.' }

Write-Host '1/8 schema check'
$ok = & sqlcmd -S $SqlInstance -E -d $Database -h -1 -W -Q "SET NOCOUNT ON; SELECT CASE WHEN OBJECT_ID('dbo.nmv_change_queue','U') IS NOT NULL AND OBJECT_ID('dbo.trg_nmv_OrderManagement_track','TR') IS NOT NULL THEN 'OK' ELSE 'MISSING' END"
if ($ok.Trim() -ne 'OK') { throw "Integration schema missing in $Database. Run sql\001_nmv_integration_install.sql first." }

Write-Host '2/8 stop existing service (if any)'
$existing = Get-Service $svc -ErrorAction SilentlyContinue
if ($existing -and $existing.Status -ne 'Stopped') { Stop-Service $svc -Force; (Get-Service $svc).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(60)) }

Write-Host "3/8 copy binaries to $InstallDir"
New-Item -ItemType Directory -Force $InstallDir | Out-Null
Copy-Item (Join-Path $pkg 'bin\NMVSyncAgent.exe'), (Join-Path $pkg 'bin\Newtonsoft.Json.dll') $InstallDir -Force

Write-Host "4/8 config in $data (existing config and secrets are kept)"
New-Item -ItemType Directory -Force $data, (Join-Path $data 'logs') | Out-Null
if (-not (Test-Path (Join-Path $data 'agent.json'))) { Copy-Item (Join-Path $pkg 'config\agent.json') (Join-Path $data 'agent.json') }

Write-Host '5/8 register service (virtual account, delayed auto start, restart on failure)'
$bin = '"' + (Join-Path $InstallDir 'NMVSyncAgent.exe') + '"'
if (-not $existing) {
    & sc.exe create $svc binPath= $bin start= delayed-auto obj= $acct DisplayName= 'NMV Sync Agent' | Out-Null
} else {
    & sc.exe config $svc binPath= $bin start= delayed-auto obj= $acct | Out-Null
}
if ($LASTEXITCODE) { throw "sc.exe failed ($LASTEXITCODE)" }
& sc.exe description $svc 'NMV store integration: POS->OrderNMC sync, HO orders in, order results out (HTTPS). Does not change the VB app.' | Out-Null
& sc.exe failure $svc reset= 86400 actions= restart/60000/restart/60000/restart/300000 | Out-Null
& sc.exe failureflag $svc 1 | Out-Null

Write-Host '6/8 file permissions (SYSTEM, Administrators, service account only)'
& icacls $data /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' "${acct}:(OI)(CI)M" | Out-Null
& icacls $InstallDir /grant "${acct}:(OI)(CI)RX" | Out-Null

Write-Host '7/8 SQL access for the service account (no sa, no password)'
& sqlcmd -S $SqlInstance -E -b -v DB=$Database -i (Join-Path $pkg 'sql\002_grant_agent_account.sql') | Out-Null
if ($LASTEXITCODE) { throw 'SQL grant failed' }

Write-Host '8/8 verify'
$env:NMV_AGENT_HOME = $null
& (Join-Path $InstallDir 'NMVSyncAgent.exe') --verify
if ($LASTEXITCODE -ne 0) { throw 'Verification failed; service not started.' }
if (-not $NoStart) { Start-Service $svc; (Get-Service $svc).WaitForStatus('Running', [TimeSpan]::FromSeconds(60)); Write-Host 'Service running.' }

# Settings shortcut (Start menu, all users)
$lnk = Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\NMV Sync Agent Settings.lnk'
$sh = New-Object -ComObject WScript.Shell; $s = $sh.CreateShortcut($lnk)
$s.TargetPath = Join-Path $InstallDir 'NMVSyncAgent.exe'; $s.Arguments = '--settings'; $s.WorkingDirectory = $InstallDir; $s.Save()
Write-Host "Done. Logs: $data\logs   Settings: Start menu > NMV Sync Agent Settings (run as administrator)"
