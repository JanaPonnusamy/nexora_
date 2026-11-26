<#
Deploys the latest Stock Client (NEXORA-MEDIQ) to a remote PC.
SMS user seeding is a SEPARATE step, run from the dev machine — see the
printed commands at the end. This script performs NO database mutation.

Run as: Administrator PowerShell, LOCALLY ON THE REMOTE TARGET PC
(or via a remote session/Device Controller terminal already open on it).

Confirmed facts (verified this session, not assumed):
  - Port 8445 (122.252.246.181) is .80's OWN backend API + its public static
    "updates" mount — used here ONLY to fetch the installer file. It is NOT
    the SMS tenant's HO.
  - Port 8444 (122.252.246.181) is .32's public HO — the correct production
    API endpoint for the SMS tenant stores (SMA/SMF/SMG/SHP). Verified /health
    200 on both ports.
  - The Electron Stock Client has NO on-disk config.json. apiBaseUrl/tenantId
    are stored in Chromium localStorage (key `nexora.desktop.settings`,
    default apiBaseUrl http://192.168.10.73:8000 — see src/state/session.js),
    written only via the app's own Settings screen. There is no supported
    file a deployment script can edit to pre-seed these values. First-run
    server config MUST be done once, manually, inside the app's Settings UI
    after install (or via a documented --dev-api-base env override at build
    time, which does not apply to a shipped installer).
  - package.json nsis block: oneClick:false, perMachine:true,
    allowToChangeInstallationDirectory:true. For an electron-builder
    perMachine NSIS installer, the supported silent switch is plain `/S`
    (no /AllUsers /CurrentUser — those apply only to non-perMachine builds
    and are not meaningful here).
  - .32 dbo.stores (tenant SMS) confirmed: SMA, SMF, SMG, SHP all exist and
    is_active=1. SHP has is_warehouse=1 (it's the SMS warehouse store, not a
    retail outlet) — PURCHASE_MANAGER can still bind to it as a store role,
    so the seeding command works unchanged, but confirm with the owner that
    a warehouse-bound PM login is actually wanted for SHP before running it.
  - dbo.roles has PURCHASE_MANAGER (role_id 0AE06EC0-59C9-4B6F-BB88-9559842564C7).

Prereqs already done on the dev machine (.80):
  - Installer staged publicly, sha256-verified, reachable (HTTP 200) at the
    URL below.
#>

param(
    [string]$InstallerUrl = "http://122.252.246.181:8445/updates/sms-fleet-deploy-20261121/NEXORA-MEDIQ-Setup-0.1.72.exe",
    [string]$ExpectedSha256 = "443e071d8bbcb374d942e28dbf9402de5a2e78a9360a5bd71f15acc9adfed021",
    [string]$HoUrl = "http://122.252.246.181:8444",
    [string]$Tenant = "SMS"
)

$ErrorActionPreference = "Stop"
$results = @{}

function Report($step, $ok, $msg) {
    $results[$step] = @{ ok = $ok; msg = $msg }
    $tag = if ($ok) { "OK" } else { "FAIL" }
    Write-Host "[$tag] $step - $msg"
}

# 1-2. Download + verify
try {
    $dest = Join-Path $env:TEMP "NEXORA-MEDIQ-Setup-latest.exe"
    Invoke-WebRequest -Uri $InstallerUrl -OutFile $dest -UseBasicParsing
    $actualSha = (Get-FileHash -Path $dest -Algorithm SHA256).Hash.ToLower()
    if ($actualSha -ne $ExpectedSha256.ToLower()) {
        Report "download+verify" $false "sha256 mismatch: got $actualSha"
        throw "Installer verification failed"
    }
    Report "download+verify" $true "sha256 OK ($dest)"
} catch {
    Report "download+verify" $false $_.Exception.Message
    throw
}

# 3. Silent install
try {
    $proc = Start-Process -FilePath $dest -ArgumentList "/S" -Wait -PassThru
    if ($proc.ExitCode -ne 0) { throw "installer exit code $($proc.ExitCode)" }
    Report "silent-install" $true "NSIS /S completed"
} catch {
    Report "silent-install" $false $_.Exception.Message
    throw
}

# 4. Server config - NOT file-based. Confirmed: the app stores apiBaseUrl/
# tenantId in Chromium localStorage, written only via its own Settings screen.
# No supported external file exists to pre-seed this, so the script cannot
# silently configure it. This step is a manual action, recorded here as a
# reminder rather than skipped silently.
Report "server-config" $false `
    "MANUAL STEP REQUIRED: launch Stock Client, open Settings, set Server URL = $HoUrl, Tenant = $Tenant, then sign in once to confirm connectivity."

# 8. Connectivity check
try {
    $health = Invoke-RestMethod -Uri "$HoUrl/health" -TimeoutSec 10
    Report "connectivity" $true "HO /health = $($health.status)"
} catch {
    Report "connectivity" $false $_.Exception.Message
}

Write-Host ""
Write-Host "=== Deployment summary ==="
foreach ($k in $results.Keys) {
    $r = $results[$k]
    Write-Host ("{0,-20} {1,-5} {2}" -f $k, $(if ($r.ok) {"OK"} else {"FAIL"}), $r.msg)
}
Write-Host ""
Write-Host "NOTE: SMS user seeding (step 5/6/7) must run from a machine with ODBC access"
Write-Host "to 192.168.10.32 (the backend/scripts/ python env), NOT from this remote PC."
Write-Host "Run on the dev machine (.80) instead:"
Write-Host '  cd backend'
Write-Host '  .venv\Scripts\python.exe scripts\create_testsms_admin.py --username SMA --password sms@123 --first-name SMA --last-name "Purchase Manager" --role PURCHASE_MANAGER --stores SMA --tenant SMS'
Write-Host '  .venv\Scripts\python.exe scripts\create_testsms_admin.py --username SMF --password sms@123 --first-name SMF --last-name "Purchase Manager" --role PURCHASE_MANAGER --stores SMF --tenant SMS'
Write-Host '  .venv\Scripts\python.exe scripts\create_testsms_admin.py --username SMG --password sms@123 --first-name SMG --last-name "Purchase Manager" --role PURCHASE_MANAGER --stores SMG --tenant SMS'
Write-Host '  .venv\Scripts\python.exe scripts\create_testsms_admin.py --username SHP --password sms@123 --first-name SHP --last-name "Purchase Manager" --role PURCHASE_MANAGER --stores SHP --tenant SMS'
