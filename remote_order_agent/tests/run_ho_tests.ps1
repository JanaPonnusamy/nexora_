# End-to-end agent ↔ HO-stub tests against OrderNMC_IntTest ONLY.
$ErrorActionPreference = 'Stop'
$root  = 'D:\VBDOTNET\NMVSyncAgent'
$exe   = "$root\bin\NMVSyncAgent.exe"
$home_ = "$root\testhome"
$state = "$root\testhome\stub"
$S     = 'DESKTOP-2\SQLEXPRESSORDER'
$DB    = 'OrderNMC_IntTest'
$port  = 18765
$env:NMV_AGENT_HOME = $home_
$results = New-Object System.Collections.ArrayList
$stub = $null

function Q([string]$sql) { (& sqlcmd -S $S -E -d $DB -b -h -1 -W -Q ("SET NOCOUNT ON; " + $sql) | Where-Object { $_ -ne '' } | Select-Object -First 1).Trim() }
function X([string]$sql) { & sqlcmd -S $S -E -d $DB -b -Q ("SET NOCOUNT ON; " + $sql) | Out-Null; if ($LASTEXITCODE) { throw "sql failed: $sql" } }
function Check([string]$name, [bool]$pass, [string]$detail = '') { [void]$results.Add([pscustomobject]@{ Test = $name; Result = $(if ($pass) { 'PASS' } else { 'FAIL' }); Detail = $detail }) }
function Agent([string]$job) { $out = & $exe --once $job 2>&1 | Out-String; $code = $LASTEXITCODE; Add-Content "$state\agent_runs.log" "== $job exit=$code`n$out"; return $code }
function StartStub([string]$scenario) { StopStub; $script:stub = Start-Process -FilePath "$root\tests\bin\HoStub.exe" -ArgumentList $port, $scenario, $state -PassThru -WindowStyle Hidden; Start-Sleep -Milliseconds 800 }
function StopStub { if ($script:stub -and -not $script:stub.HasExited) { $script:stub.Kill(); $script:stub.WaitForExit() }; $script:stub = $null }
function VbEdit([string]$sql) { & sqlcmd -S $S -E -d $DB -b -Q $sql | Out-Null }   # plain session, exactly like the VB app

function NewOrder([long]$orderId, [int]$version, [int]$count, [string]$store = 'NMV') {
    $rows = & sqlcmd -S $S -E -d $DB -h -1 -W -s '|' -Q "SET NOCOUNT ON; SELECT TOP $count ProductCode, REPLACE(ProductName,'|',' '), ISNULL(TotalStock,0), ISNULL(SaleUnit,1), ISNULL(MRP,0), ISNULL(ProductType,1) FROM dbo.Products WHERE StoreName='NMV' AND isActive=1 ORDER BY ProductCode"
    $lines = @()
    foreach ($r in ($rows | Where-Object { $_ -match '\|' })) {
        $c = $r.Split('|'); $pt = [int]([double]$c[5] -ne 0)
        $lines += [ordered]@{ product_code = [long]$c[0]; product_name = $c[1]; total_stock = [double]$c[2]; sale_unit = [double]$c[3]; purchase_price = $null; mrp = [double]$c[4]
            sub_location = $null; unit_description = $null; last_received_date = $null; last_sale_date = $null; transaction_date = $null; wanted_date = $null
            sls_qty = 10; max_sale_qty = 2; wanted_type = 'Regular Order Based Min & Max'; status = 0; order_qty = 2 + ($lines.Count % 3); org_order_qty = $null
            product_type = $pt; product_type_name = $(if ($pt -eq 1) { 'Pharma' } else { 'Non Pharma' }); min_qty = 5; max_qty = 9; frequence = 3; remarks = $null }
    }
    # independent implementation of the contract hash
    $canon = ($lines | Sort-Object { $_.product_code } | ForEach-Object { "{0}|{1}|{2}|{3}|{4}" -f $_.product_code, $_.order_qty, $_.order_qty, $_.status, $_.product_type }) -join "`n"
    $sha = [Security.Cryptography.SHA256]::Create(); $hash = -join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($canon)) | ForEach-Object { $_.ToString('x2') })
    $order = [ordered]@{ order_id = $orderId; version = $version; store_code = $store; order_no = $null; order_datetime = (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz')
        min_days = 15; max_days = 20; last_sale_bill_no = $null; last_bill_datetime = $null; last_grn = $null; line_count = $lines.Count; lines_sha256 = $hash; lines = $lines }
    ($order | ConvertTo-Json -Depth 5) | Set-Content -Encoding utf8 "$state\order.json"
}

try {
    # ---------- setup
    Remove-Item -Recurse -Force $state -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Force $state | Out-Null
    Remove-Item "$home_\secrets.dat" -ErrorAction SilentlyContinue
    $cfg = Get-Content "$home_\agent.json" -Raw | ConvertFrom-Json
    $cfg | Add-Member -Force ho_enabled $true; $cfg | Add-Member -Force ho_base_url "http://localhost:$port"; $cfg | Add-Member -Force allow_insecure_http $true
    $cfg | Add-Member -Force order_replace_quiet_minutes 0
    $cfg | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 "$home_\agent.json"
    X "SET CONTEXT_INFO 0x4E4D565F4147454E54; DELETE FROM dbo.OrderManagement; DELETE FROM dbo.OrderManagementBackup; DELETE FROM dbo.OrderHeaderDetails;
       INSERT INTO dbo.OrderManagement SELECT * FROM OrderNMC.dbo.OrderManagement WHERE StoreName='NMV';
       INSERT INTO dbo.OrderHeaderDetails SELECT * FROM OrderNMC.dbo.OrderHeaderDetails WHERE OrderId IN (SELECT OrderId FROM dbo.OrderManagement);
       SET CONTEXT_INFO 0x; DELETE FROM dbo.nmv_change_queue; DELETE FROM dbo.nmv_order_inbox;"
    $legacyRows = [int](Q "SELECT COUNT(*) FROM dbo.OrderManagement")
    $O1 = 900000000000001

    # ---------- 1 invalid auth during enrollment, then enrollment
    StartStub 'normal'
    'WRONG-CODE' | & $exe --enroll | Out-Null; Check 'enroll: wrong one-time code refused' ($LASTEXITCODE -ne 0)
    'ENROLL-TEST-1' | & $exe --enroll | Out-Null; Check 'enroll: device credentials stored (DPAPI)' ($LASTEXITCODE -eq 0 -and (Test-Path "$home_\secrets.dat"))
    $sec = Get-Content "$home_\secrets.dat" -Raw
    Check 'secrets file holds no plaintext token' (-not $sec.Contains('test-device-token-0001'))

    # ---------- 2 order download → appears in OrderManagement
    NewOrder $O1 1 40
    $code = Agent 'orders_pull'
    Check 'order pull exit 0' ($code -eq 0) "exit=$code"
    Check 'order applied: 40 lines in OrderManagement' ([int](Q "SELECT COUNT(*) FROM dbo.OrderManagement WHERE OrderId=$O1") -eq 40)
    Check 'previous order removed from OrderManagement' ([int](Q "SELECT COUNT(*) FROM dbo.OrderManagement WHERE OrderId<>$O1") -eq 0)
    $arch = [int](Q "SELECT COUNT(*) FROM dbo.OrderManagementBackup")
    Check 'previous real order archived to OrderManagementBackup' ($arch -eq $legacyRows) "archived=$arch legacy=$legacyRows"
    Check 'OrderHeaderDetails row created' ([int](Q "SELECT COUNT(*) FROM dbo.OrderHeaderDetails WHERE OrderId=$O1 AND StoreName='NMV' AND MinDays=15") -eq 1)
    Check 'header LastSaleBillNo/LastGRN filled from POS' ([int](Q "SELECT COUNT(*) FROM dbo.OrderHeaderDetails WHERE OrderId=$O1 AND LastSaleBillNo IS NOT NULL AND LastGRN IS NOT NULL") -eq 1)
    Check 'VB fields: Status=''0'', Qtycheck=0, OrgOrderQty=OrderQty' ([int](Q "SELECT COUNT(*) FROM dbo.OrderManagement WHERE OrderId=$O1 AND Status='0' AND Qtycheck=0 AND OrgOrderQty=OrderQty AND StoreCode=10") -eq 40)
    Check 'VB Qty Check query sees the order' ([int](Q "SELECT COUNT(*) FROM ordermanagement WHERE qtycheck = 0 AND producttypename IN ('Pharma', 'Non Pharma') AND storename = 'NMV' AND status = 0") -eq 40)
    Check 'inbox APPLIED + ACKED' ((Q "SELECT state+'/'+ack_state FROM dbo.nmv_order_inbox WHERE order_id=$O1") -eq 'APPLIED/ACKED')
    Check 'agent writes produced no queue rows (no echo)' ([int](Q "SELECT COUNT(*) FROM dbo.nmv_change_queue") -eq 0)
    Check 'HO received APPLIED ack with matching hash' ((Get-Content "$state\acks.log" | Select-Object -Last 1) -match '"state":"APPLIED"')

    # ---------- 3 duplicate download
    $code = Agent 'orders_pull'
    Check 'duplicate download: no change to OrderManagement' ([int](Q "SELECT COUNT(*) FROM dbo.OrderManagement") -eq 40)
    Check 'duplicate download: OrderManagementBackup unchanged' ([int](Q "SELECT COUNT(*) FROM dbo.OrderManagementBackup") -eq $arch)
    Check 'duplicate download: still one inbox row' ([int](Q "SELECT COUNT(*) FROM dbo.nmv_order_inbox") -eq 1)

    # ---------- 4 VB edits → queue → push → ack
    $p1 = Q "SELECT MIN(ProductCode) FROM dbo.OrderManagement"; $p2 = Q "SELECT MAX(ProductCode) FROM dbo.OrderManagement"
    VbEdit "UPDATE ordermanagement SET orderqty = 9, remarks = 'OrderQty Changed 6 Add', qtycheck = 1 WHERE productcode = $p1 AND storename = 'NMV' AND status = 0"
    VbEdit "UPDATE ordermanagement SET orderqty = 0, remarks = 'Don''t want to Order', qtycheck = 1 WHERE productcode = $p2 AND storename = 'NMV' AND status = 0"
    VbEdit "UPDATE ordermanagement SET orqty = 9, orsupplier = 'ABC PHARMA', orsuppliercode = '101', status = 1 WHERE productcode = $p1 AND status = 0 AND storename = 'NMV'"
    Check 'qty edit / remarks / supplier assignment queued (3)' ([int](Q "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='PENDING'") -eq 3)
    $code = Agent 'results_push'
    Check 'result upload: all 3 ACKED' ([int](Q "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='ACKED'") -eq 3) "exit=$code"
    $last = Get-Content "$state\results.log" | Select-Object -Last 1 | ConvertFrom-Json
    Check 'HO payload carries before/after + order/product' ($last.items[2].after.or_supplier_code -eq '101' -and $last.items[2].before.status -eq '0' -and $last.items[2].after.status -eq '1' -and [long]$last.items[0].order_id -eq $O1)

    # ---------- 5 duplicate upload (ack lost locally) → HO answers duplicates → ACKED, HO not double-applied
    X "UPDATE dbo.nmv_change_queue SET sync_state='PENDING', acked_at=NULL"
    $code = Agent 'results_push'
    $last = Get-Content "$state\results.log" | Select-Object -Last 1 | ConvertFrom-Json
    Check 'duplicate upload: same batch_id reused' ($last.batch_id -eq (Get-Content "$state\results.log" | Select-Object -First 1 | ConvertFrom-Json).batch_id)
    Check 'duplicate upload: re-ACKED via HO duplicates list' ([int](Q "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='ACKED'") -eq 3)

    # ---------- 6 Internet down: VB keeps working, queue grows, nothing lost; reconnect drains
    StopStub
    VbEdit "UPDATE ordermanagement SET orderqty = 4, remarks = 'OrderQty Changed 1 Add', qtycheck = 1 WHERE productcode = (SELECT TOP 1 ProductCode FROM dbo.OrderManagement WHERE Status='0' AND Qtycheck=0 ORDER BY ProductCode) AND storename = 'NMV' AND status = 0"
    Check 'offline: VB edit succeeds locally' ($LASTEXITCODE -eq 0)
    $code = Agent 'results_push'
    Check 'offline: push fails (network) without losing the edit' ($code -ne 0 -and [int](Q "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='PENDING'") -eq 1) "exit=$code"
    Check 'offline: error recorded on queue row' ([int](Q "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='PENDING' AND last_error LIKE 'network%'") -eq 1)
    StartStub 'normal'
    $code = Agent 'results_push'
    Check 'reconnect: queue drained and ACKED' ([int](Q "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='PENDING'") -eq 0) "exit=$code"

    # ---------- 7 HO commits but response lost → retry is safe
    StartStub 'lost_response'
    VbEdit "UPDATE ordermanagement SET remarks = 'OrderQty Changed 1 Less' WHERE productcode = $p2 AND storename = 'NMV'"
    $c1 = Agent 'results_push'; $c2 = Agent 'results_push'
    $dupLine = Get-Content "$state\results.log" | Select-Object -Last 1
    Check 'lost response: first attempt failed, retry ACKED' ($c1 -ne 0 -and $c2 -eq 0 -and [int](Q "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='PENDING'") -eq 0)
    Check 'lost response: HO saw the item twice but stored it once' (((Get-Content "$state\seen_changes.txt") | Group-Object | Where-Object Count -gt 1).Count -eq 0)

    # ---------- 8 partial batch: one final reject, one accepted
    StartStub 'partial'
    VbEdit "UPDATE ordermanagement SET orderqty = 6 WHERE productcode = $p1 AND storename = 'NMV'"
    VbEdit "UPDATE ordermanagement SET orderqty = 1 WHERE productcode = $p2 AND storename = 'NMV'"
    $code = Agent 'results_push'
    Check 'partial batch: 1 REJECTED (kept), 1 ACKED' ([int](Q "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='REJECTED'") -eq 1 -and [int](Q "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='PENDING'") -eq 0)

    # ---------- 9 malformed acknowledgement → nothing marked
    StartStub 'bad_ack'
    VbEdit "UPDATE ordermanagement SET orderqty = 7 WHERE productcode = $p1 AND storename = 'NMV'"
    VbEdit "UPDATE ordermanagement SET orderqty = 2 WHERE productcode = $p2 AND storename = 'NMV'"
    $code = Agent 'results_push'
    Check 'invalid ack (ids missing): batch NOT marked, stays PENDING' ($code -ne 0 -and [int](Q "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='PENDING'") -eq 2)
    StartStub 'normal'; $null = Agent 'results_push'

    # ---------- 10 wrong store identity in responses
    StartStub 'wrong_store'
    VbEdit "UPDATE ordermanagement SET orderqty = 8 WHERE productcode = $p1 AND storename = 'NMV'"
    $code = Agent 'results_push'
    Check 'wrong store in HO response: rejected, nothing ACKED' ($code -ne 0 -and [int](Q "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='PENDING'") -eq 1)

    # ---------- 11 invalid authentication (revoked device)
    StartStub 'auth401'
    $code = Agent 'results_push'
    Check 'auth failure: push fails, edit kept PENDING' ($code -ne 0 -and [int](Q "SELECT COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state='PENDING'") -eq 1)
    $code = Agent 'orders_pull'
    Check 'auth failure: order pull fails, OrderManagement untouched' ($code -ne 0 -and [int](Q "SELECT COUNT(*) FROM dbo.OrderManagement") -eq 40)

    # ---------- 12 corrupted payload (hash mismatch)
    StartStub 'corrupt'
    $code = Agent 'orders_pull'
    Check 'corrupted order: OrderManagement untouched' ([int](Q "SELECT COUNT(*) FROM dbo.OrderManagement WHERE OrderId=$O1") -eq 40 -and [int](Q "SELECT SUM(CAST(OrderQty AS int)) FROM dbo.OrderManagement WHERE Status='0' AND Qtycheck=0") -gt 0)
    Check 'corrupted order: HASH_MISMATCH reported to HO' ((Get-Content "$state\acks.log" | Select-Object -Last 1) -match 'HASH_MISMATCH')
    Check 'corrupted order: APPLIED inbox row not overwritten' ((Q "SELECT state FROM dbo.nmv_order_inbox WHERE order_id=$O1 AND version=1") -eq 'APPLIED')

    # ---------- 13 amendment after user edits → refused
    StartStub 'order_v2'
    $code = Agent 'orders_pull'
    Check 'amendment v2 refused: USER_EDITS_EXIST' ((Q "SELECT reason_code FROM dbo.nmv_order_inbox WHERE order_id=$O1 AND version=2") -eq 'USER_EDITS_EXIST')

    # ---------- 14 new order while edits un-acknowledged → DEFERRED, then applied after drain
    StartStub 'normal'
    $O2 = 900000000000002; NewOrder $O2 1 25
    X "UPDATE dbo.nmv_change_queue SET sync_state='PENDING' WHERE change_id = (SELECT MAX(change_id) FROM dbo.nmv_change_queue)"
    $code = Agent 'orders_pull'
    Check 'new order deferred while previous order has un-acked edits' ((Q "SELECT state FROM dbo.nmv_order_inbox WHERE order_id=$O2") -eq 'DEFERRED' -and [int](Q "SELECT COUNT(*) FROM dbo.OrderManagement WHERE OrderId=$O1") -eq 40)
    $null = Agent 'results_push'; $code = Agent 'orders_pull'
    Check 'deferred order applied after queue drained' ((Q "SELECT state FROM dbo.nmv_order_inbox WHERE order_id=$O2 AND version=1") -eq 'APPLIED' -and [int](Q "SELECT COUNT(*) FROM dbo.OrderManagement") -eq 25)
    Check 'edited order archived with user edits preserved' ([int](Q "SELECT COUNT(*) FROM dbo.OrderManagementBackup WHERE OrderId=$O1 AND OrSupplierCode='101' AND Status='1'") -eq 1)

    # ---------- 15 wrong store code in order
    $O3 = 900000000000003; NewOrder $O3 1 5 'NMC'
    $code = Agent 'orders_pull'
    Check 'order for another store rejected: WRONG_STORE' ((Q "SELECT reason_code FROM dbo.nmv_order_inbox WHERE order_id=$O3") -eq 'WRONG_STORE' -and [int](Q "SELECT COUNT(*) FROM dbo.OrderManagement") -eq 25)

    # ---------- 16 heartbeat + verify
    $code = Agent 'heartbeat'
    Check 'heartbeat accepted and reports queue' ($code -eq 0 -and (Test-Path "$state\last_heartbeat.json"))
    & $exe --verify | Out-File "$state\verify.txt"
    Check 'verify passes on test DB' ($LASTEXITCODE -eq 0) (Get-Content "$state\verify.txt" | Select-String FAIL | Out-String)
    $logs = Get-Content "$home_\logs\*.log" -Raw
    Check 'logs contain no token/secret/password values' (-not ($logs -match 'test-device-token-0001|test-device-secret-0001|ENROLL-TEST-1'))
}
finally {
    StopStub
    $results | Format-Table -AutoSize | Out-String -Width 200
    $f = @($results | Where-Object Result -eq 'FAIL').Count
    "TOTAL={0} PASS={1} FAIL={2}" -f $results.Count, ($results.Count - $f), $f
}
