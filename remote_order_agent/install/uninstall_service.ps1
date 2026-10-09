# Removes the NMVSyncAgent service. Config, secrets and logs in %ProgramData%\NMVSyncAgent are kept unless -RemoveData.
# The SQL change queue is NOT touched (use sql\001_nmv_integration_rollback.sql for that).
param([string]$InstallDir = 'D:\NMVSyncAgent', [switch]$RemoveData)
$ErrorActionPreference = 'Stop'
$svc = 'NMVSyncAgent'
if (Get-Service $svc -ErrorAction SilentlyContinue) {
    Stop-Service $svc -Force -ErrorAction SilentlyContinue
    & sc.exe delete $svc | Out-Null
    Write-Host 'Service removed.'
}
Remove-Item (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\NMV Sync Agent Settings.lnk') -ErrorAction SilentlyContinue
Remove-Item $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
if ($RemoveData) { Remove-Item (Join-Path $env:ProgramData 'NMVSyncAgent') -Recurse -Force; Write-Host 'Config, secrets and logs removed.' }
