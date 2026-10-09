# Exercises the modified VB module (from the separately built exe) via reflection. Test DB only, except the
# read-only health check, which now only logs.
$ErrorActionPreference = 'Stop'
$asm = [Reflection.Assembly]::LoadFrom('D:\VBDOTNET\NMVSyncAgent\vb_build\OrderManagement.exe')
$mod = $asm.GetType('WindowsApplication1.SQL_Connection_Module')
$bf  = [Reflection.BindingFlags]'Static,Public,NonPublic'
$S   = 'DESKTOP-2\SQLEXPRESSORDER'
$res = New-Object System.Collections.ArrayList
function Check($n, $p, $d = '') { [void]$res.Add([pscustomobject]@{ Test = $n; Result = $(if ($p) { 'PASS' } else { 'FAIL' }); Detail = $d }) }
function SetConn($cs) { $mod.GetField('destinationConnectionString', $bf).SetValue($null, $cs) }
function Flags($store) { $a = [object[]]@($store, $false, $false); [void]$mod.GetMethod('GetIntegrationFlags', $bf).Invoke($null, $a); return ,@($a[1], $a[2]) }

SetConn "Data Source=$S;Initial Catalog=OrderNMC_IntTest;Integrated Security=True"
$f = Flags 'NMV';  Check 'NMV is managed (Process Order/Sync hidden)' ($f[0] -eq $true)
Check 'NMV Web Export disabled by default' ($f[1] -eq $false)
$f = Flags 'NMC';  Check 'other store (NMC) not managed — unchanged behaviour' ($f[0] -eq $false -and $f[1] -eq $true)
& sqlcmd -S $S -E -d OrderNMC_IntTest -Q "UPDATE dbo.nmv_integration_store SET AllowWebExport=1 WHERE StoreName='NMV'" | Out-Null
$f = Flags 'NMV';  Check 'AllowWebExport=1 re-enables Web Export for NMV' ($f[0] -eq $true -and $f[1] -eq $true)
& sqlcmd -S $S -E -d OrderNMC_IntTest -Q "UPDATE dbo.nmv_integration_store SET AllowWebExport=0 WHERE StoreName='NMV'" | Out-Null
SetConn "Data Source=$S;Initial Catalog=stkEnquiry;Integrated Security=True"
$f = Flags 'NMV';  Check 'database without integration table: not managed' ($f[0] -eq $false)
SetConn "Data Source=$S;Initial Catalog=NoSuchDb_x;Integrated Security=True;Connect Timeout=3"
$f = Flags 'NMV';  Check 'check fails (DB unreachable): fail-safe = managed (destructive ops blocked)' ($f[0] -eq $true -and $f[1] -eq $false)

# health check: must not repair. 'Order' database does not exist on this instance -> previously triggered repair path.
$log = 'D:\OrderDotNet\Log\DBStatus.log'
$before = if (Test-Path $log) { (Get-Content $log).Count } else { 0 }
$mod.GetField('destinationConnectionStringinstant', $bf).SetValue($null, "Data Source=$S;Initial Catalog=master;Integrated Security=True")
$mod.GetField('serverName', $bf).SetValue($null, $S)
[void]$mod.GetMethod('CheckDatabaseStatusAndConnect', $bf).Invoke($null, $null)
$new = Get-Content $log | Select-Object -Skip $before
Check 'health check ran' ($new.Count -gt 0) ($new -join ' / ')
Check 'no KILL / EMERGENCY / SINGLE_USER / DBCC executed' (-not ($new -match 'Killing|EMERGENCY|SINGLE_USER|DBCC|Starting emergency'))
Check 'missing Order database only logged' ($new -match "Database 'Order' not found on this server. No action taken.")
$st = & sqlcmd -S $S -E -h -1 -W -Q "SET NOCOUNT ON; SELECT state_desc+'/'+user_access_desc FROM sys.databases WHERE name='OrderNMC'"
Check 'live OrderNMC still ONLINE/MULTI_USER' ($st.Trim() -eq 'ONLINE/MULTI_USER')
$src = Get-Content 'D:\VBDOTNET\OrderManagement\OrderManagement\SQL_Connection_Module.vb' -Raw
Check 'hard-coded sa login removed from VB source' (-not ($src -match 'User ID=sa'))

$res | Format-Table -AutoSize | Out-String -Width 200
"TOTAL={0} FAIL={1}" -f $res.Count, @($res | Where-Object Result -eq 'FAIL').Count
