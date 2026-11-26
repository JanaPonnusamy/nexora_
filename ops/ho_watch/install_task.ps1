<#
  Registers the "NexoraHoWatch" scheduled task for the CURRENT user:
    * starts at logon and again every 5 hours (a new 5-hour watch session each time)
    * never runs two sessions at once (IgnoreNew), hidden, no time limit
  Runs as the logged-on user because the Claude CLI sign-in lives in that profile.
  Remove with:  Unregister-ScheduledTask -TaskName NexoraHoWatch -Confirm:$false
#>
$script = Join-Path $PSScriptRoot 'run_watch.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$logon  = New-ScheduledTaskTrigger -AtLogOn
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Hours 5)
$set    = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName 'NexoraHoWatch' -Action $action -Trigger @($logon, $repeat) -Settings $set `
  -Description 'Nexora HO + database watcher (read-only). Fresh 5-hour session; Claude diagnoses only on change.' -Force | Out-Null
Get-ScheduledTask -TaskName 'NexoraHoWatch' | Select-Object TaskName, State
