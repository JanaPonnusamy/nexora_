# Elevated restart of the Nexora production backend on :8000.
# Stops the current (possibly --reload) uvicorn tree, then relaunches the
# stable production launcher (start-prod-8000.bat, no --reload) and verifies
# health. Writes a result log this session can read back.
$ErrorActionPreference = 'Continue'
$log = 'E:\Nexora\backend\logs\restart_admin.log'
New-Item -ItemType Directory -Force -Path 'E:\Nexora\backend\logs' | Out-Null
function Log($m) { $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m; Add-Content -Path $log -Value $line -Encoding utf8 }

Set-Content -Path $log -Value "=== restart run $(Get-Date) ===" -Encoding utf8
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
Log "Elevated: $admin"

# 1. Identify + kill the process tree currently listening on :8000
$listeners = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
$pids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($p in $pids) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$p" -ErrorAction SilentlyContinue
    if ($proc) {
        Log ("Killing listener PID {0} (parent {1})" -f $p, $proc.ParentProcessId)
        # Kill the parent (uvicorn --reload watcher) with its tree so it can't respawn.
        cmd /c "taskkill /PID $($proc.ParentProcessId) /T /F" 2>&1 | ForEach-Object { Log $_ }
        cmd /c "taskkill /PID $p /T /F" 2>&1 | ForEach-Object { Log $_ }
    }
}

# 2. Wait for the port to actually free
$freed = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 500
    if (-not (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) { $freed = $true; break }
}
Log "Port 8000 freed: $freed"

# 3. Relaunch the production backend (no --reload) detached
Set-Location 'E:\Nexora\backend'
Log "Launching start-prod-8000.bat"
Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', 'E:\Nexora\backend\start-prod-8000.bat' -WorkingDirectory 'E:\Nexora\backend' -WindowStyle Hidden

# 4. Poll health for up to ~40s
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { Log ("HEALTH OK after {0}s: {1}" -f ($i+1), $r.Content); $ok = $true; break }
    } catch { }
}
if (-not $ok) { Log "HEALTH FAILED - backend did not come up within 40s" }

# 5. Record the new listener + confirm the new route is served
$newpid = (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
Log "New listener PID: $newpid"
try {
    $api = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/openapi.json' -UseBasicParsing -TimeoutSec 6
    if ($api.Content -match 'purchase-entry') { Log "ROUTE OK: /purchase-entry present in openapi" } else { Log "ROUTE MISSING: /purchase-entry not in openapi" }
} catch { Log "openapi check failed: $($_.Exception.Message)" }
Log "=== done ==="