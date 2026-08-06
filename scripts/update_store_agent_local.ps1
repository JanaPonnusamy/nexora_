#Requires -RunAsAdministrator
<#
Run this ON THE STORE PC to update the local Nexora Store Agent from the HO dist share.
#>
param(
    [string]$SourceShare = "\\192.168.10.80\E\Nexora\dist",
    [string]$AgentService = "NexoraStoreAgent",
    [string]$WatchdogService = "NexoraStoreAgentWatchdog",
    [string]$AgentExe = "NexoraStoreAgent.exe",
    [string]$SettingsExe = "NexoraStoreAgentSettings.exe",
    [string]$WatchdogExe = "NexoraStoreAgentWatchdog.exe"
)

$ErrorActionPreference = "Stop"
function Info($m) { Write-Host "[INFO] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[ OK ] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Fail($m) { throw $m }

# 1. Diagnose + fix network path access
Info "Checking network path: $SourceShare"
if (-not (Test-Path -LiteralPath $SourceShare)) {
    Warn "Path not reachable. Running diagnostics..."
    $hostAddr = "192.168.10.80"
    Test-Connection -ComputerName $hostAddr -Count 2 | Format-Table
    Write-Host "--- nslookup ---"; nslookup $hostAddr 2>$null
    Write-Host "--- port 445 (SMB) check ---"
    $tcp = Test-NetConnection -ComputerName $hostAddr -Port 445
    $tcp | Format-Table ComputerName,RemotePort,TcpTestSucceeded

    if (-not $tcp.TcpTestSucceeded) {
        Fail "Cannot reach $hostAddr on SMB port 445 (firewall/routing/host down). Fix network connectivity, then re-run."
    }

    Warn "Host reachable but share/path failed - likely a permissions or credential issue."
    Warn "Attempting to map the share explicitly (you may be prompted for HO server credentials)."
    net use \\$hostAddr\E /persistent:no 2>&1 | Write-Host

    if (-not (Test-Path -LiteralPath $SourceShare)) {
        Fail "Still cannot access $SourceShare after mapping \\$hostAddr\E. Check share permissions on the HO server (Everyone/Authenticated Users read access on E share and NTFS perms on Nexora\dist), and that SMB client is enabled here (Get-WindowsOptionalFeature -Online -FeatureName SMB1Protocol / SMB signing policy mismatch)."
    }
}
Ok "Network path accessible: $SourceShare"

foreach ($f in @($AgentExe, $SettingsExe, $WatchdogExe)) {
    if (-not (Test-Path -LiteralPath (Join-Path $SourceShare $f))) {
        Fail "Missing on source share: $f"
    }
}

# 2. Locate the local install path from the existing service's binPath
function Get-ServiceBinDir($name) {
    $qc = & sc.exe qc $name
    $line = $qc | Select-String "BINARY_PATH_NAME"
    if (-not $line) { Fail "Could not query service '$name' - is it installed?" }
    $binPath = ($line.ToString() -split ":\s*",2)[1].Trim().Trim('"')
    return (Split-Path $binPath -Parent)
}

$installDir = Get-ServiceBinDir -name $AgentService
Info "Detected install directory: $installDir"

# 3. Stop services + kill leftovers
Info "Stopping services..."
Stop-Service -Name $AgentService -Force -ErrorAction SilentlyContinue
Stop-Service -Name $WatchdogService -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
taskkill /IM $AgentExe /F 2>$null | Out-Null
taskkill /IM $WatchdogExe /F 2>$null | Out-Null
Start-Sleep -Seconds 2
Ok "Old processes stopped."

# 4. Backup + copy new binaries
$backupDir = Join-Path $installDir ("backups\upgrade-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
foreach ($f in @($AgentExe, $SettingsExe, $WatchdogExe)) {
    $existing = Join-Path $installDir $f
    if (Test-Path -LiteralPath $existing) {
        Copy-Item -LiteralPath $existing -Destination (Join-Path $backupDir $f) -Force
    }
}
Ok "Backed up old binaries to $backupDir"

Info "Copying new binaries from $SourceShare..."
Copy-Item -LiteralPath (Join-Path $SourceShare $AgentExe)    -Destination (Join-Path $installDir $AgentExe)    -Force
Copy-Item -LiteralPath (Join-Path $SourceShare $SettingsExe) -Destination (Join-Path $installDir $SettingsExe) -Force
Copy-Item -LiteralPath (Join-Path $SourceShare $WatchdogExe) -Destination (Join-Path $installDir $WatchdogExe) -Force
Ok "New binaries copied."

# 5. Both services are already configured start= auto (launch at system boot).
#    Re-assert it in case a prior manual change disabled it.
& sc.exe config $AgentService start= auto | Out-Null
& sc.exe config $WatchdogService start= auto | Out-Null

# 6. Start services
Info "Starting services..."
Start-Service -Name $AgentService
Start-Service -Name $WatchdogService
Start-Sleep -Seconds 3

Write-Host ""
Ok "Update complete."
Get-Service $AgentService, $WatchdogService | Format-Table Name, Status, StartType
