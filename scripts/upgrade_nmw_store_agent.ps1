$ErrorActionPreference = "Stop"

$repoRoot = "E:\Nexora"
$installPath = "D:\NexoraStoreAgent"
$agentExe = "NexoraStoreAgent.exe"
$settingsExe = "NexoraStoreAgentSettings.exe"
$watchdogExe = "NexoraStoreAgentWatchdog.exe"
$agentService = "NexoraStoreAgent"
$watchdogService = "NexoraStoreAgentWatchdog"

$currentReleaseDir = Get-ChildItem -Path (Join-Path $repoRoot "backend\agent_releases") -Directory -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$installedVersion = if ($currentReleaseDir) { $currentReleaseDir.Name } else { "1.0.0" }

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $installPath ("backups\upgrade-" + $timestamp)
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

foreach ($name in @($agentExe, $settingsExe, $watchdogExe, "agent_version_installed.txt")) {
    $src = Join-Path $installPath $name
    if (Test-Path $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $backupDir $name) -Force
    }
}

Write-Host "Stopping services..."
if (Get-Service -Name $agentService -ErrorAction SilentlyContinue) {
    Stop-Service -Name $agentService -Force
}
if (Get-Service -Name $watchdogService -ErrorAction SilentlyContinue) {
    Stop-Service -Name $watchdogService -Force
}

Start-Sleep -Seconds 3

Write-Host "Stopping leftover agent processes..."
Get-Process -Name "NexoraStoreAgent","NexoraStoreAgentWatchdog" -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 2

Write-Host "Copying fresh binaries..."
Copy-Item -LiteralPath (Join-Path $repoRoot "dist\$agentExe") -Destination (Join-Path $installPath $agentExe) -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "dist\$settingsExe") -Destination (Join-Path $installPath $settingsExe) -Force
Copy-Item -LiteralPath (Join-Path $repoRoot "dist\$watchdogExe") -Destination (Join-Path $installPath $watchdogExe) -Force
Set-Content -LiteralPath (Join-Path $installPath "agent_version_installed.txt") -Value $installedVersion

Write-Host "Recreating agent service..."
sc.exe delete $agentService | Out-Null
Start-Sleep -Seconds 2
sc.exe create $agentService binPath= "`"$installPath\$agentExe`"" start= auto DisplayName= "Nexora Store Agent" obj= "LocalSystem" | Out-Null
sc.exe config $agentService start= auto | Out-Null
sc.exe description $agentService "Nexora Store Agent: heartbeats to HO and runs delta sync tasks." | Out-Null
sc.exe failure $agentService reset= 86400 actions= restart/60000/restart/60000/restart/60000 | Out-Null

Write-Host "Recreating watchdog service..."
sc.exe delete $watchdogService | Out-Null
Start-Sleep -Seconds 2
sc.exe create $watchdogService binPath= "`"$installPath\$watchdogExe`"" start= auto DisplayName= "Nexora Store Agent Watchdog" obj= "LocalSystem" | Out-Null
sc.exe config $watchdogService start= auto | Out-Null
sc.exe description $watchdogService "Nexora Store Agent Watchdog: keeps the agent updated and running." | Out-Null
sc.exe failure $watchdogService reset= 86400 actions= restart/60000/restart/60000/restart/60000 | Out-Null

Write-Host "Starting services..."
sc.exe start $agentService | Out-Null
sc.exe start $watchdogService | Out-Null

Write-Host ""
Write-Host "Upgrade complete."
Write-Host "Backup:" $backupDir
Write-Host "Installed version marker:" $installedVersion
Write-Host ""
sc.exe query $agentService
sc.exe query $watchdogService
