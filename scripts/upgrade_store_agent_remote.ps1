param(
    [Parameter(Mandatory = $true)]
    [string]$ComputerName,

    [Parameter(Mandatory = $true)]
    [string]$RemoteSharePath,

    [string]$RepoRoot = "E:\Nexora",
    [string]$RemoteInstallLocalPath = "D:\NexoraStoreAgent",
    [string]$AgentService = "NexoraStoreAgent",
    [string]$WatchdogService = "NexoraStoreAgentWatchdog",
    [string]$AgentExe = "NexoraStoreAgent.exe",
    [string]$SettingsExe = "NexoraStoreAgentSettings.exe",
    [string]$WatchdogExe = "NexoraStoreAgentWatchdog.exe",
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"

function Info($message) {
    Write-Host "[INFO] $message" -ForegroundColor Cyan
}

function Ok($message) {
    Write-Host "[ OK ] $message" -ForegroundColor Green
}

function Fail($message) {
    throw $message
}

function Test-RemoteShare {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        Fail "Remote share path not reachable: $Path"
    }
}

function Get-InstalledVersion {
    param([string]$Root, [string]$ExplicitVersion)
    if ($ExplicitVersion) {
        return $ExplicitVersion
    }

    $releaseRoot = Join-Path $Root "backend\agent_releases"
    $releaseDir = Get-ChildItem -Path $releaseRoot -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($releaseDir) {
        return $releaseDir.Name
    }

    $exe = Join-Path $Root "dist\NexoraStoreAgent.exe"
    if (Test-Path -LiteralPath $exe) {
        return (Get-Item -LiteralPath $exe).LastWriteTime.ToString("yyyy.MM.dd.HHmm")
    }

    return "unknown"
}

function Stop-ServiceRemote {
    param([string]$ScTarget, [string]$Name)
    & sc.exe $ScTarget stop $Name | Out-Null
}

function Delete-ServiceRemote {
    param([string]$ScTarget, [string]$Name)
    & sc.exe $ScTarget delete $Name | Out-Null
}

function Create-ServiceRemote {
    param(
        [string]$ScTarget,
        [string]$Name,
        [string]$DisplayName,
        [string]$Description,
        [string]$BinPath
    )
    & sc.exe $ScTarget create $Name binPath= "`"$BinPath`"" start= auto DisplayName= $DisplayName obj= "LocalSystem" | Out-Null
    & sc.exe $ScTarget config $Name start= auto | Out-Null
    & sc.exe $ScTarget description $Name $Description | Out-Null
    & sc.exe $ScTarget failure $Name reset= 86400 actions= restart/60000/restart/60000/restart/60000 | Out-Null
}

function Start-ServiceRemote {
    param([string]$ScTarget, [string]$Name)
    & sc.exe $ScTarget start $Name | Out-Null
}

function Query-ServiceRemote {
    param([string]$ScTarget, [string]$Name)
    & sc.exe $ScTarget query $Name
}

$distRoot = Join-Path $RepoRoot "dist"
$agentSource = Join-Path $distRoot $AgentExe
$settingsSource = Join-Path $distRoot $SettingsExe
$watchdogSource = Join-Path $distRoot $WatchdogExe

foreach ($required in @($agentSource, $settingsSource, $watchdogSource)) {
    if (-not (Test-Path -LiteralPath $required)) {
        Fail "Build artifact not found: $required"
    }
}

Test-RemoteShare -Path $RemoteSharePath

$scTarget = "\\$ComputerName"
$versionMarker = Get-InstalledVersion -Root $RepoRoot -ExplicitVersion $Version
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $RemoteSharePath ("backups\upgrade-" + $timestamp)

Info "Target machine: $ComputerName"
Info "Remote copy path: $RemoteSharePath"
Info "Remote service path: $RemoteInstallLocalPath"
Info "Version marker: $versionMarker"

New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
Ok "Backup directory ready: $backupDir"

foreach ($name in @($AgentExe, $SettingsExe, $WatchdogExe, "agent_version_installed.txt")) {
    $current = Join-Path $RemoteSharePath $name
    if (Test-Path -LiteralPath $current) {
        Copy-Item -LiteralPath $current -Destination (Join-Path $backupDir $name) -Force
    }
}
Ok "Existing binaries backed up."

Info "Stopping remote services..."
Stop-ServiceRemote -ScTarget $scTarget -Name $AgentService
Stop-ServiceRemote -ScTarget $scTarget -Name $WatchdogService
Start-Sleep -Seconds 3

Info "Stopping leftover remote processes..."
& taskkill.exe /S $ComputerName /IM $AgentExe /F | Out-Null
& taskkill.exe /S $ComputerName /IM $WatchdogExe /F | Out-Null
Start-Sleep -Seconds 2

Info "Copying fresh binaries to the remote share..."
Copy-Item -LiteralPath $agentSource -Destination (Join-Path $RemoteSharePath $AgentExe) -Force
Copy-Item -LiteralPath $settingsSource -Destination (Join-Path $RemoteSharePath $SettingsExe) -Force
Copy-Item -LiteralPath $watchdogSource -Destination (Join-Path $RemoteSharePath $WatchdogExe) -Force
Set-Content -LiteralPath (Join-Path $RemoteSharePath "agent_version_installed.txt") -Value $versionMarker -Encoding ascii
Ok "Fresh binaries copied."

Info "Recreating remote services..."
Delete-ServiceRemote -ScTarget $scTarget -Name $AgentService
Delete-ServiceRemote -ScTarget $scTarget -Name $WatchdogService
Start-Sleep -Seconds 2

Create-ServiceRemote `
    -ScTarget $scTarget `
    -Name $AgentService `
    -DisplayName "Nexora Store Agent" `
    -Description "Nexora Store Agent: heartbeats to HO and runs delta sync tasks." `
    -BinPath (Join-Path $RemoteInstallLocalPath $AgentExe)

Create-ServiceRemote `
    -ScTarget $scTarget `
    -Name $WatchdogService `
    -DisplayName "Nexora Store Agent Watchdog" `
    -Description "Nexora Store Agent Watchdog: keeps the agent updated and running." `
    -BinPath (Join-Path $RemoteInstallLocalPath $WatchdogExe)

Ok "Remote services recreated."

Info "Starting remote services..."
Start-ServiceRemote -ScTarget $scTarget -Name $AgentService
Start-ServiceRemote -ScTarget $scTarget -Name $WatchdogService
Start-Sleep -Seconds 3

Write-Host ""
Ok "Remote upgrade complete."
Write-Host "Backup: $backupDir"
Write-Host "Installed version marker: $versionMarker"
Write-Host ""
Query-ServiceRemote -ScTarget $scTarget -Name $AgentService
Query-ServiceRemote -ScTarget $scTarget -Name $WatchdogService
