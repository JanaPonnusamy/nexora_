<#
  ho_watchdog.ps1 - keeps the UniNexHO backend up on an EXE node.

  Registered by update_ho_node.ps1 as the SYSTEM scheduled task
  "NexoraHOWatchdog", firing every minute. Each run:

    * If a FRESH maintenance flag is present  -> stand down (an update is in
      progress). A STALE flag (> MaxMaintenanceMinutes) is treated as an
      abandoned update: cleared, then recovery proceeds.
    * Else health-check http://127.0.0.1:<port>/health. If it is not 200, log
      WHY (service state + recent Application event-log errors) and immediately
      start / restart the service, then re-check.

  Lives in C:\ProgramData\NexoraHO so it survives backend bundle swaps.
#>
[CmdletBinding()]
param(
    [string]$ServiceName          = 'UniNexHO',
    [int]   $HoPort               = 8000,
    [int]   $MaxMaintenanceMinutes = 15
)

$stable = 'C:\ProgramData\NexoraHO'
New-Item -ItemType Directory -Force -Path $stable | Out-Null
$flag = Join-Path $stable 'maintenance.flag'
$log  = Join-Path $stable 'watchdog.log'
function Log($m){ "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Add-Content -Path $log -Encoding utf8 }

# --- maintenance-aware: stand down while an update is running -------------
if (Test-Path $flag) {
    $age = (Get-Date) - (Get-Item $flag).LastWriteTime
    if ($age.TotalMinutes -lt $MaxMaintenanceMinutes) {
        Log ("maintenance in progress ({0}m) - standing down" -f [int]$age.TotalMinutes)
        return
    }
    Log ("stale maintenance flag ({0}m) - clearing, recovering" -f [int]$age.TotalMinutes)
    Remove-Item $flag -Force -ErrorAction SilentlyContinue
}

# --- health check ---------------------------------------------------------
$healthy = $false
try {
    if ((Invoke-WebRequest "http://127.0.0.1:$HoPort/health" -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200) {
        $healthy = $true
    }
} catch {}
if ($healthy) { return }   # quiet when all is well

# --- down: diagnose why ---------------------------------------------------
$svc = Get-Service $ServiceName -ErrorAction SilentlyContinue
$state = if ($svc) { $svc.Status } else { 'NOT-INSTALLED' }
Log "HO DOWN: /health != 200; service state = $state"
try {
    Get-WinEvent -FilterHashtable @{ LogName='Application'; Level=2; StartTime=(Get-Date).AddMinutes(-15) } `
        -MaxEvents 8 -ErrorAction SilentlyContinue |
        Where-Object { $_.Message -match 'UniNexHO|HO_Backend|uvicorn|BACKEND CRASH' } |
        ForEach-Object { Log ("  evt {0}: {1}" -f $_.TimeCreated, ($_.Message -split "`n")[0].Trim()) }
} catch {}

# --- recover: start / restart immediately ---------------------------------
try {
    if ($state -eq 'NOT-INSTALLED') { Log 'service not installed - cannot recover'; return }
    if ($state -eq 'Running') {
        Log 'service Running but not serving (hung) - restarting'
        Restart-Service $ServiceName -Force -ErrorAction Stop
    } else {
        Log "starting service (was $state)"
        Start-Service $ServiceName -ErrorAction Stop
    }
} catch {
    Log "recovery start failed: $($_.Exception.Message)"
    return
}

# --- verify recovery ------------------------------------------------------
Start-Sleep -Seconds 8
try {
    $code = (Invoke-WebRequest "http://127.0.0.1:$HoPort/health" -UseBasicParsing -TimeoutSec 5).StatusCode
    Log "after recovery: HTTP $code"
} catch {
    Log "after recovery: still down - $($_.Exception.Message)"
}
