<#
.SYNOPSIS
    Prepare, install, register and verify one UniNex Store Agent for the
    Sharadha tenant. Reuses the existing Store Agent runtime + HO API; does not
    redesign anything.

.DESCRIPTION
    Per store the script:
      1. Tests the HO endpoint.
      2. Resolves tenant_id + store_id automatically from HO by store_code
         (GET /api/tenants, GET /api/stores/tenant/{id}) - no manual DB editing.
      3. Writes the Store Agent configuration file (agent_config.json) with the
         resolved identity and the HO URL.
      4. Installs the Windows service (sc.exe, start=auto, restart-on-failure)
         from the deployed NexoraStoreAgent.exe - same hardening as
         store_agent_setup.service_manager.
      5. Starts the service.
      6. Verifies registration + heartbeat with HO (agent.log).
      7. Verifies the first synchronization cycle (agent.log).

    SQL credentials are NOT entered here: they are already held (encrypted) in
    HO by seed_sharadha_stores.sql, and the agent fetches them at runtime via
    GET /api/stores/{store_id}/agent-config.

.EXAMPLE
    # Full deploy (agent files already laid down by StoreAgent_Setup.exe, or via -AgentDist)
    .\deploy_store_agent.ps1 -StoreCode SMA

.EXAMPLE
    # Lay down the agent files from a built distribution, then deploy
    .\deploy_store_agent.ps1 -StoreCode SMG -AgentDist D:\dist\NexoraStoreAgent

.EXAMPLE
    # Only (re)write the config + verify (service already installed by the wizard)
    .\deploy_store_agent.ps1 -StoreCode SMF -SkipInstall
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('SMG', 'SMA', 'SMF')]
    [string]$StoreCode,

    [string]$HoUrl       = 'https://ho.qvault.in',
    [string]$TenantName  = 'Sharadha',
    [string]$InstallPath = 'D:\NexoraStoreAgent',
    [string]$LogLevel    = 'INFO',
    [string]$AgentDist   = '',          # optional: built NexoraStoreAgent folder to copy
    [switch]$SkipInstall,               # only write config + verify
    [int]$VerifyTimeoutSec = 180
)

$ErrorActionPreference = 'Stop'
$ServiceName = 'NexoraStoreAgent'
$AgentExe    = 'NexoraStoreAgent.exe'

function Info($m)  { Write-Host "[deploy] $m" -ForegroundColor Cyan }
function Ok($m)    { Write-Host "[ OK ] $m"   -ForegroundColor Green }
function Fail($m)  { Write-Host "[FAIL] $m"   -ForegroundColor Red; exit 1 }

# Fall back to C:\ if the default D:\ drive is absent.
if (-not (Test-Path (Split-Path $InstallPath -Qualifier)) -and
    $InstallPath -like 'D:\*') {
    $InstallPath = $InstallPath -replace '^D:', 'C:'
    Info "D: not present - using $InstallPath"
}

# ---- 1. HO reachability ----------------------------------------------------
Info "Testing HO at $HoUrl ..."
try {
    $health = Invoke-RestMethod -Uri "$HoUrl/health" -TimeoutSec 20
} catch {
    Fail "HO not reachable at $HoUrl/health : $($_.Exception.Message)"
}
if ("$($health.status)".ToLower() -ne 'healthy') { Fail "HO reported unhealthy: $($health | ConvertTo-Json -Compress)" }
Ok "HO reachable and healthy."

# ---- 2. Resolve tenant + store automatically -------------------------------
Info "Resolving tenant '$TenantName' ..."
$tenants = Invoke-RestMethod -Uri "$HoUrl/api/tenants" -TimeoutSec 20
$tenant = $tenants | Where-Object {
    $_.tenant_name -eq $TenantName -or
    $_.tenant_code -eq $TenantName -or
    $_.tenant_abbreviation -eq $TenantName
} | Select-Object -First 1
if (-not $tenant) { Fail "Tenant '$TenantName' not found in HO." }
$tenantId = $tenant.tenant_id
Ok "tenant_id = $tenantId"

Info "Resolving store '$StoreCode' ..."
$stores = Invoke-RestMethod -Uri "$HoUrl/api/stores/tenant/$tenantId" -TimeoutSec 20
$store = $stores | Where-Object { $_.store_code -eq $StoreCode } | Select-Object -First 1
if (-not $store) {
    Fail "Store '$StoreCode' not found for tenant '$TenantName'. Run seed_sharadha_stores.sql against HO first."
}
$storeId   = $store.store_id
$storeName = $store.store_name
Ok "store_id = $storeId  ($storeName)"

# ---- 3. Lay down agent files (optional copy) -------------------------------
# -AgentDist accepts either a onefile exe directly (current build) or a
# legacy onedir folder (exe + _internal) for back-compat.
if ($AgentDist) {
    New-Item -ItemType Directory -Force -Path $InstallPath | Out-Null
    if ((Test-Path $AgentDist -PathType Leaf) -and ($AgentDist -like "*$AgentExe")) {
        Info "Copying single agent exe to $InstallPath ..."
        Copy-Item $AgentDist -Destination (Join-Path $InstallPath $AgentExe) -Force
        Ok "Agent exe deployed."
    } elseif (Test-Path (Join-Path $AgentDist $AgentExe)) {
        Info "Copying agent distribution folder to $InstallPath ..."
        Copy-Item (Join-Path $AgentDist '*') -Destination $InstallPath -Recurse -Force
        Ok "Agent files deployed."
    } else {
        Fail "AgentDist '$AgentDist' is neither $AgentExe nor a folder containing it."
    }
}

$exePath = Join-Path $InstallPath $AgentExe
if (-not $SkipInstall -and -not (Test-Path $exePath)) {
    Fail "$AgentExe not found at $InstallPath. Run StoreAgent_Setup.exe first, or pass -AgentDist."
}

# ---- 4. Write the agent configuration file ---------------------------------
Info "Writing agent_config.json ..."
New-Item -ItemType Directory -Force -Path $InstallPath | Out-Null
$config = [ordered]@{
    ho_url       = $HoUrl
    tenant_id    = $tenantId
    tenant_name  = $tenant.tenant_name
    store_id     = $storeId
    store_name   = $storeName
    store_code   = $StoreCode
    install_path = $InstallPath
    log_level    = $LogLevel
}
$config | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $InstallPath 'agent_config.json')
Ok "Configuration written for $StoreCode -> $HoUrl"

# ---- 5/6. Install + start the Windows service ------------------------------
function Get-ServiceState {
    $q = (& sc.exe query $ServiceName) 2>$null
    if ($LASTEXITCODE -ne 0) { return 'absent' }
    if ($q -match 'RUNNING') { return 'running' }
    if ($q -match 'STOPPED') { return 'stopped' }
    return 'unknown'
}

if (-not $SkipInstall) {
    Info "Registering Windows service '$ServiceName' ..."
    if ((Get-ServiceState) -ne 'absent') {
        & sc.exe stop $ServiceName | Out-Null
        Start-Sleep -Seconds 2
        & sc.exe delete $ServiceName | Out-Null
        Start-Sleep -Seconds 2
    }
    & sc.exe create $ServiceName binPath= "`"$exePath`"" start= auto `
        DisplayName= "Nexora Store Agent" obj= LocalSystem | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "sc create failed (run as Administrator)." }
    & sc.exe config $ServiceName start= auto | Out-Null
    & sc.exe failure $ServiceName reset= 86400 `
        actions= restart/60000/restart/60000/restart/60000 | Out-Null
    Ok "Service registered (startup=auto, restart-on-failure)."

    Info "Starting service ..."
    & sc.exe start $ServiceName | Out-Null
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline -and (Get-ServiceState) -ne 'running') { Start-Sleep 2 }
    if ((Get-ServiceState) -ne 'running') {
        Fail "Service did not reach RUNNING. See $InstallPath\logs\agent.log and the Event Log."
    }
    Ok "Service running."
} else {
    Info "SkipInstall set - leaving service as-is (state: $(Get-ServiceState))."
}

# ---- 7. Verify heartbeat + first sync (agent.log is the source of truth) ---
$agentLog = Join-Path $InstallPath 'logs\agent.log'

function Wait-ForLog([string[]]$patterns, [string]$what, [int]$timeoutSec) {
    Info "Verifying $what (up to ${timeoutSec}s) ..."
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $agentLog) {
            $text = Get-Content $agentLog -Raw -ErrorAction SilentlyContinue
            foreach ($p in $patterns) { if ($text -match $p) { return $true } }
        }
        Start-Sleep 3
    }
    return $false
}

if (Wait-ForLog @('\[AGENT\] registered', 'registered store') 'registration + heartbeat' $VerifyTimeoutSec) {
    Ok "Agent registered with HO (heartbeat established)."
} else {
    Fail "No registration/heartbeat seen in $agentLog within ${VerifyTimeoutSec}s."
}

if (Wait-ForLog @('\[SYNC\] cycle', '\[CATALOG\] delta') 'first synchronization' $VerifyTimeoutSec) {
    Ok "First synchronization cycle completed."
} else {
    Write-Host "[WARN] No sync cycle seen yet in $agentLog within ${VerifyTimeoutSec}s." -ForegroundColor Yellow
    Write-Host "       The agent is registered; sync runs on its schedule - re-check the log shortly." -ForegroundColor Yellow
}

Write-Host ""
Ok "Store $StoreCode ($storeName) deployed against $HoUrl."
Write-Host "    store_id  : $storeId"
Write-Host "    install   : $InstallPath"
Write-Host "    log       : $agentLog"
