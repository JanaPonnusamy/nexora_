<#
  HO + database watcher: one "session" = WindowHours of checks every IntervalMinutes.

  Every cycle runs ho_probe.py (plain, no AI, read-only). When the set of problems
  CHANGES, it starts a fresh READ-ONLY Claude session (Read/Grep/Glob only, no Bash,
  no edits) to diagnose from the facts and the saved runbooks, writes a report to
  logs\ho_watch\, and sends a WhatsApp alert. When everything clears it sends a
  "resolved" line. Same problems are re-sent at most every ResendHours.

  Nothing here repairs anything. Task Scheduler (install_task.ps1) starts the next
  session when this one ends, and at boot.
#>
param(
  [int]$IntervalMinutes = 10,
  [double]$WindowHours = 5,
  [double]$ResendHours = 6,
  [int]$ClaudeTimeoutSeconds = 300,
  [switch]$Once
)

$ErrorActionPreference = 'Continue'
$Root   = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Py     = Join-Path $Root 'backend\.venv\Scripts\python.exe'
$Probe  = Join-Path $PSScriptRoot 'ho_probe.py'
$Send   = Join-Path $PSScriptRoot 'send_alert.py'
$LogDir = Join-Path $Root 'logs\ho_watch'
$State  = Join-Path $LogDir 'state.json'
$Log    = Join-Path $LogDir 'watch.log'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Log($msg) { "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg | Add-Content -Path $Log -Encoding UTF8 }

function Get-State {
  if (Test-Path $State) { try { return Get-Content $State -Raw | ConvertFrom-Json } catch {} }
  [pscustomobject]@{ signature = ''; lastSent = ''; }
}
function Save-State($sig, $sent, $diag = '', $diagAt = '') { [pscustomobject]@{ signature = $sig; lastSent = $sent; diag = $diag; diagAt = $diagAt; diagSig = $sig } | ConvertTo-Json | Set-Content $State -Encoding UTF8 }

function Invoke-Probe {
  $raw = & $Py $Probe 2>$null
  try { return ($raw -join "`n" | ConvertFrom-Json) } catch { return $null }
}

function Send-WhatsApp([string]$text) {
  $text | & $Py $Send 2>&1 | ForEach-Object { Log "whatsapp: $_" }
  return ($LASTEXITCODE -eq 0)
}

function Get-ClaudeDiagnosis([string]$factsFile) {
  $claude = Get-Command claude -ErrorAction SilentlyContinue
  if (-not $claude) { Log 'claude CLI not found; skipping diagnosis'; return $null }
  $prompt = @"
You are the read-only HO and database watcher for Nexora. Facts from the latest probe are in:
$factsFile
Read that file. Then, in at most 12 short lines:
1. First line exactly: STATUS: PROBLEM   (or STATUS: OK if nothing is wrong)
2. What is down or degraded, and since when if the facts say.
3. The most likely cause, using the project's saved runbooks/memory where they match (for example SQL Express memory cap, RECOVERY_PENDING database, gutted venv, stuck sync, machine powered off).
4. The ONE safest next step for a human. Do not run or suggest destructive actions.
You may only read files. Do not attempt to change, restart, kill or repair anything.
"@
  $job = Start-Job -ArgumentList $claude.Source, $prompt, $Root -ScriptBlock {
    param($exe, $text, $dir)
    Set-Location $dir
    $text | & $exe -p --model sonnet --allowedTools Read Grep Glob --disallowedTools Bash Write Edit NotebookEdit --max-turns 8 2>&1
    "__EXIT__$LASTEXITCODE"
  }
  if (-not (Wait-Job $job -Timeout $ClaudeTimeoutSeconds)) { Stop-Job $job; Remove-Job $job -Force; Log 'claude diagnosis timed out'; return $null }
  $lines = @(Receive-Job $job); Remove-Job $job -Force
  $exit = ($lines | Where-Object { $_ -is [string] -and $_ -like '__EXIT__*' } | Select-Object -Last 1)
  $text = (($lines | Where-Object { -not ($_ -is [string] -and $_ -like '__EXIT__*') }) | ForEach-Object { "$_" }) -join "`n"
  if ($exit -ne '__EXIT__0' -or -not $text.Trim()) { Log ("claude diagnosis failed ({0}): {1}" -f $exit, ($text -replace '\s+', ' ')); return $null }
  return $text
}

$end = (Get-Date).AddHours($WindowHours)
Log "session start: every $IntervalMinutes min until $($end.ToString('HH:mm'))"

do {
  $facts = Invoke-Probe
  if (-not $facts) { Log 'probe produced no JSON'; Start-Sleep -Seconds 60; continue }

  $problems = @($facts.problems)
  $sig = (($problems | Sort-Object) -join '|')
  $st = Get-State
  $stamp = Get-Date
  Log ("{0}: {1}" -f $facts.status, ($(if ($problems.Count) { $problems -join '; ' } else { 'all good' })))

  $lastSent = if ($st.lastSent) { [datetime]$st.lastSent } else { [datetime]::MinValue }
  $changed  = ($sig -ne $st.signature)
  $resend   = ($problems.Count -gt 0 -and ($stamp - $lastSent).TotalHours -ge $ResendHours)

  if ($problems.Count -gt 0 -and ($changed -or $resend)) {
    $factsFile = Join-Path $LogDir ('facts_{0}.json' -f $stamp.ToString('yyyyMMdd_HHmm'))
    ($facts | ConvertTo-Json -Depth 8) | Set-Content $factsFile -Encoding UTF8
    $cached = ($st.diag -and $st.diagSig -eq $sig -and $st.diagAt -and ($stamp - [datetime]$st.diagAt).TotalMinutes -lt ($ResendHours * 60))
    $diag = if ($cached) { $st.diag } else { Get-ClaudeDiagnosis $factsFile }
    $report = Join-Path $LogDir ('report_{0}.md' -f $stamp.ToString('yyyyMMdd_HHmm'))
    $body = @("# HO watch $($stamp.ToString('yyyy-MM-dd HH:mm'))", '', '## Problems', ($problems | ForEach-Object { "- $_" }), '', '## Diagnosis', $(if ($diag) { $diag } else { '(Claude diagnosis unavailable; plain probe result only)' }))
    $body | Set-Content $report -Encoding UTF8
    $msg = @("NEXORA HO WATCH - $($stamp.ToString('dd-MMM HH:mm'))", ($problems | ForEach-Object { "- $_" }))
    if ($diag) { $msg += ''; $msg += (($diag -split "`n" | Select-Object -First 12) -join "`n") }
    $sent = Send-WhatsApp (($msg -join "`n"))
    Log ("alert {0}; report {1}" -f $(if ($sent) { 'sent' } else { 'NOT sent' }), (Split-Path $report -Leaf))
    # Only remember it as sent when WhatsApp confirmed, so a missing session never swallows an alert.
    Save-State $sig $(if ($sent) { $stamp.ToString('o') } else { $st.lastSent }) $(if ($diag) { $diag } else { '' }) $stamp.ToString('o')
  }
  elseif ($problems.Count -eq 0 -and $st.signature) {
    $sent = Send-WhatsApp ("NEXORA HO WATCH - $($stamp.ToString('dd-MMM HH:mm'))`nRESOLVED: all HOs and the database look healthy.")
    Log ("resolved notice {0}" -f $(if ($sent) { 'sent' } else { 'NOT sent' }))
    Save-State '' ''
  }

  if ($Once) { break }
  Start-Sleep -Seconds ($IntervalMinutes * 60)
} while ((Get-Date) -lt $end)

Log 'session end'
