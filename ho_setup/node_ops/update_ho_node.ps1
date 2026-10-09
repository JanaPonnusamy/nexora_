<#
  update_ho_node.ps1 - manual HO backend update for an EXE node (.73 / .32).

  Run ELEVATED on the node. Pulls the signed HO_Backend bundle from the build
  node's temporary file server, verifies it, hot-swaps it behind the UniNexHO
  service, health-checks (incl. /api/nmv/v1), rolls back on failure, and installs
  the maintenance-aware watchdog.

  The build node (.80) must be serving the releases dir first (see the setup
  block printed by Claude). Bootstrap on the node:

      iwr http://192.168.10.80:8099/update_ho_node.ps1 -OutFile $env:TEMP\u.ps1; & $env:TEMP\u.ps1
#>
[CmdletBinding()]
param(
    [string]$BuildHost   = '192.168.10.80',
    [int]   $FilePort    = 8099,
    [int]   $HoPort      = 8000,
    [string]$ServiceName = 'UniNexHO',
    [switch]$SkipWatchdog
)

$ErrorActionPreference = 'Stop'
function Say($m){ Write-Host "[update] $m" }
function Die($m){ Write-Host "[update] ERROR: $m" -ForegroundColor Red; exit 1 }

# --- 0. must be elevated --------------------------------------------------
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Die 'run this in an ELEVATED PowerShell (Run as administrator).' }

$stable = 'C:\ProgramData\NexoraHO'
New-Item -ItemType Directory -Force -Path $stable | Out-Null
$flag = Join-Path $stable 'maintenance.flag'

# --- 1. locate the install dir from the service binPath -------------------
$svc = Get-CimInstance Win32_Service -Filter "Name='$ServiceName'" -ErrorAction SilentlyContinue
if (-not $svc) { Die "service '$ServiceName' not found on this node." }
$raw = $svc.PathName
if     ($raw -match '"([^"]+\.exe)"') { $exePath = $matches[1] }
elseif ($raw -match '(\S+\.exe)')     { $exePath = $matches[1] }
else { Die "could not parse exe path from service binPath: $raw" }
$installDir = Split-Path $exePath -Parent
if (-not (Test-Path (Join-Path $installDir 'HO_Backend.exe'))) {
    Die "HO_Backend.exe not found in install dir '$installDir'."
}
Say "install dir: $installDir"

# --- 2. read the published manifest from the build node -------------------
$base = "http://${BuildHost}:$FilePort"
try   { $latest = Invoke-RestMethod -Uri "$base/latest.json" -TimeoutSec 20 }
catch { Die "cannot reach build node file server at $base/latest.json - is it serving? ($($_.Exception.Message))" }
$version = $latest.version
$zipName = $latest.file_name
$sha     = ($latest.sha256).ToLower()
if (-not $version) { Die 'latest.json has no version.' }
Say "published version: $version ($zipName)"

$curVer = $null
$marker = Join-Path $installDir 'HO_BACKEND_VERSION.txt'
if (Test-Path $marker) { $curVer = (Get-Content $marker -Raw).Trim() }
Say "current version: $curVer"
if ($curVer -eq $version) {
    Say "already on $version - skipping swap, will (re)install watchdog only."
}

# --- 3. raise the maintenance flag (watchdog stands down) -----------------
Set-Content -Path $flag -Value "updating to $version @ $(Get-Date -Format o) pid=$PID" -Encoding utf8
Say 'maintenance flag raised.'

try {
    if ($curVer -ne $version) {
        # --- 4. download the bundle ---------------------------------------
        $stage = Join-Path $env:TEMP 'nexora-ho-update'
        New-Item -ItemType Directory -Force -Path $stage | Out-Null
        $zip = Join-Path $stage $zipName
        Say "downloading $base/$version/$zipName ..."
        Invoke-WebRequest -Uri "$base/$version/$zipName" -OutFile $zip -TimeoutSec 900
        $sizeMB = [math]::Round((Get-Item $zip).Length / 1MB, 1)
        Say "downloaded $sizeMB MB."

        # --- 5. verify sha256 ---------------------------------------------
        $actual = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower()
        if ($actual -ne $sha) { Die "sha256 mismatch: expected $sha got $actual" }
        Say 'sha256 verified.'

        # --- 6. stop the service ------------------------------------------
        Say "stopping $ServiceName ..."
        Stop-Service $ServiceName -Force -ErrorAction SilentlyContinue
        for ($i=0; $i -lt 20; $i++) {
            if ((Get-Service $ServiceName).Status -eq 'Stopped') { break }
            Start-Sleep -Seconds 1
        }

        # --- 7. back up current code (exclude runtime/config dirs) --------
        $backup = Join-Path $stage 'backup'
        if (Test-Path $backup) { Remove-Item $backup -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $backup | Out-Null
        Say 'backing up current install ...'
        robocopy $installDir $backup /E /XD logs uploads backups config /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { Die "backup robocopy failed (code $LASTEXITCODE)" }

        # --- 8. swap in the new bundle ------------------------------------
        Say 'expanding new bundle over install ...'
        Expand-Archive -Force -LiteralPath $zip -DestinationPath $installDir

        # --- 9. start + health check --------------------------------------
        Say "starting $ServiceName ..."
        Start-Service $ServiceName
        $healthy = $false
        for ($i=0; $i -lt 45; $i++) {
            try {
                if ((Invoke-WebRequest "http://127.0.0.1:$HoPort/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) {
                    $healthy = $true; break
                }
            } catch {}
            Start-Sleep -Seconds 2
        }
        $nmv = 0
        if ($healthy) {
            try {
                $spec = Invoke-RestMethod "http://127.0.0.1:$HoPort/openapi.json" -TimeoutSec 10
                $nmv = @($spec.paths.PSObject.Properties.Name | Where-Object { $_ -like '/api/nmv/v1/*' }).Count
            } catch {}
        }

        # --- 10. rollback if unhealthy or routes missing ------------------
        if (-not $healthy -or $nmv -lt 1) {
            Say "health=$healthy nmv_routes=$nmv -> ROLLING BACK"
            Stop-Service $ServiceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 4
            robocopy $backup $installDir /E /NFL /NDL /NJH /NJS /NP | Out-Null
            Start-Service $ServiceName
            Die "update failed (health=$healthy, nmv_routes=$nmv); rolled back to $curVer."
        }
        Say "update OK: now on $version, health=200, nmv_routes=$nmv."
    }
}
finally {
    Remove-Item $flag -Force -ErrorAction SilentlyContinue
    Say 'maintenance flag cleared.'
}

# --- 11. install / refresh the watchdog -----------------------------------
if (-not $SkipWatchdog) {
    Say 'installing watchdog ...'
    $wd = Join-Path $stable 'ho_watchdog.ps1'
    Invoke-WebRequest -Uri "$base/ho_watchdog.ps1" -OutFile $wd -TimeoutSec 60
    $tr = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$wd`" -ServiceName $ServiceName -HoPort $HoPort"
    # every minute, as SYSTEM; schtasks.exe works where Register-ScheduledTask is denied.
    schtasks.exe /Create /TN NexoraHOWatchdog /TR $tr /SC MINUTE /MO 1 /RU SYSTEM /RL HIGHEST /F | Out-Null
    # also harden the service's own crash recovery (belt + suspenders).
    sc.exe failure $ServiceName reset= 60 actions= restart/5000/restart/5000/restart/10000 | Out-Null
    Say 'watchdog installed (NexoraHOWatchdog, every 1 min, SYSTEM).'
}

Say "DONE on $(hostname). Version=$version."
