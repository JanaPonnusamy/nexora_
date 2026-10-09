# NMV Integration — Implementation Report (2026-10-08)

Package: `D:\VBDOTNET\NMVSyncAgent`. Design: `01_NMV_Integration_Design.md`. HO contract: `02_HO_API_Contract.md`.

## Deployment state at hand-over

| Item | State |
|---|---|
| Integration schema + trigger in live `OrderNMC` | **Installed** (additive). Queue empty, 586-line order intact, `--verify` OK |
| NMVSyncAgent Windows service | **Built, not installed.** Run `install\install_service.ps1` when approved |
| Guarded VB build | **Built** to `vb_build\OrderManagement.exe`. **Not deployed**; the store still runs the original builds |
| HO link | `http://122.252.246.181:8443` (as instructed). HO sync is **off** until HO implements the contract and issues an enrollment code |

## Changes made since the design document

- **HO link and Settings window.** `ho_base_url` holds the HO host. The agent appends `ho_api_prefix` (`api/nmv/v1`). The link can be changed later in Start menu → *NMV Sync Agent Settings*, or with `NMVSyncAgent.exe --settings`. That window offers Test connection, Enroll device, and Save & restart service.
- **Plain HTTP.** The link is plain HTTP, so `allow_insecure_http=true` is set. The window and the service log show a warning about this every time.
- **Delete-guard in the trigger.** Users still have older ClickOnce and Visual Studio builds that have no guard. The trigger now **refuses non-agent DELETEs** of a managed store's `OrderManagement` rows. Only VB "Process Order" issues those deletes. This protects the HO order no matter which exe is run.
- **`OrderSuppliers` not synced by default.** The legacy VB Sync MERGE into `OrderSuppliers` has **always failed silently**: it adds `Sync`/`SyncDateTime` columns that this table doesn't have, and the error only went to the Console. The agent keeps the effective behaviour (`pos_sync_ordersuppliers=false`). Turning it on would add POS suppliers with a NULL `UnifiedSupplierCode`.
- **SaleInformation merge key.** It merges on the table's real primary key `(BillDate, BNumber, StoreName)`. VB used `BillNumber+BillDate+StoreName+CustomerCode`, which could collide with the primary key.

## 1. Files created
| Path | Purpose |
|---|---|
| `docs\01_NMV_Integration_Design.md` | Dependency matrix, column contract, read/write and sync maps, schema plan, change tracking, architecture, security, failure model |
| `docs\02_HO_API_Contract.md` | API that HO must implement |
| `docs\03_Implementation_Report.md` | This report |
| `sql\001_nmv_integration_install.sql` / `…_rollback.sql` | Additive schema and trigger / rollback |
| `sql\002_grant_agent_account.sql` | SQL access for `NT SERVICE\NMVSyncAgent` |
| `src\*.cs` | Agent: Core (config, DPAPI, logging, DB), PosSync, HoClient, OrderPull, ResultPush, Agent (scheduler and service), Program (CLI), SettingsForm |
| `build.ps1`, `bin\NMVSyncAgent.exe` | Build script and output (.NET Framework 4.x; no runtime to install) |
| `config\agent.json` | Production config template (no secrets) |
| `install\install_service.ps1`, `uninstall_service.ps1`, `deploy_vb_build.ps1` | Service install/remove; VB exe deploy/rollback with backup |
| `tests\*` | Test DB create/drop, trigger tests, HO stub + end-to-end tests, VB guard tests |
| `rollback\vb_original\*.orig` | Original `Form1.vb` and `SQL_Connection_Module.vb` |
| `vb_build\OrderManagement.exe` | Guarded VB build (not deployed) |

## 2. Files modified (VB, `D:\VBDOTNET\OrderManagement\OrderManagement`)
| File | Change |
|---|---|
| `SQL_Connection_Module.vb` | (a) The startup health check no longer runs `KILL` / `SINGLE_USER` / `EMERGENCY` / `DBCC REPAIR_ALLOW_DATA_LOSS` automatically. It only logs, unless an administrator sets the registry value `HKCU\Software\OrderDotNetApp\Config\AllowAutoDbRepair="1"`. (b) The hard-coded `sa` login was removed; the configured login is used instead. (c) New `GetIntegrationFlags` / `IsIntegrationManagedStore`, which read `nmv_integration_store` and fail safe |
| `Form1.vb` | For a managed store: "Process Order" is removed from the menu and also guarded in the menu handler, `ProcessOrder()` and `InsertDataIntoDestination()`. The old Sync button is hidden and guarded. Web Export / Pull are disabled unless `AllowWebExport=1`. Nothing else was changed: no UI redesign, and the order calculation is untouched |

Behaviour for any store not listed in `nmv_integration_store`, or any database without that table, is unchanged. The one global change is that auto-repair is now opt-in.

## 3. DB scripts / migrations
`001_nmv_integration_install.sql` (idempotent, `-v DB=OrderNMC`) adds:
- `nmv_integration_store` (seeded with NMV, managed, Web Export off)
- `nmv_change_queue`
- `nmv_order_inbox`
- `nmv_sync_state` (with `queue_epoch` and `schema_version=1`)
- `nmv_sync_audit`
- the trigger `trg_nmv_OrderManagement_track`

No existing object was altered. `002_grant_agent_account.sql` is run by the installer.

## 4. Windows service installation
1. Approve and close the VB app on this PC.
2. In an elevated PowerShell: `powershell -ExecutionPolicy Bypass -File D:\VBDOTNET\NMVSyncAgent\install\install_service.ps1`
3. The installer copies to `D:\NMVSyncAgent` and creates `%ProgramData%\NMVSyncAgent\agent.json`. It registers the service `NMVSyncAgent`:
   - account: `NT SERVICE\NMVSyncAgent` (no password)
   - start: delayed auto-start, so it survives reboots
   - recovery: restart after 60 s / 60 s / 300 s
   It then locks the data folder ACL to SYSTEM, Administrators and the service account, grants SQL access, runs `--verify`, and starts the service.
4. Logs go to `%ProgramData%\NMVSyncAgent\logs\agent-YYYYMMDD.log` (30-day retention). Each run is also recorded in `dbo.nmv_sync_audit`.
5. To enable HO later: HO issues an enrollment code → *NMV Sync Agent Settings* (run as administrator) → tick *Enable HO order/result sync* → enter the code → *Enroll device* → *Save & restart service*.
6. To deploy the guarded VB build: `install\deploy_vb_build.ps1 -Target <folder staff run from>`. ClickOnce users need a re-publish from Visual Studio.

## 5. Configuration (`%ProgramData%\NMVSyncAgent\agent.json`)
No secrets are stored in this file. The main keys:

| Key | Value |
|---|---|
| Store | `store_code` NMV (enforced), `store_id` |
| Local DB | `local_server` / `local_database` (Windows auth) |
| POS | `pos_*` |
| HO | `ho_enabled`, `ho_base_url`, `ho_api_prefix`, `allow_insecure_http` |
| Push | `push_batch_size` |
| Orders | `order_replace_quiet_minutes`, `unknown_product_policy` |
| Housekeeping | `*_retention_days` |
| Schedule | `jobs.*.interval_sec` |

**POS credentials:** `pos_credential_source`
- `stores_table` (default; reuses the NMV `stores` row the VB app already uses)
- `dpapi` (`pos_username` in config, plus `echo <pwd> | NMVSyncAgent.exe --set-secret pos_password`)

**Secrets** (DPAPI LocalMachine, in `secrets.dat`): `pos_password`, `ho_device_token`, `ho_device_secret`, `ho_device_id`.

## 6. Sync schedule (defaults, configurable per job)
| Job | Lane | Every | Content |
|---|---|---|---|
| results_push | network | 30 s | Change queue → HO |
| orders_pull | network | 60 s | HO orders → OrderManagement / OrderHeaderDetails |
| heartbeat | network | 5 min | Queue depth, last runs |
| pos_incremental | local | 15 min | SaleInformation, ProductTrans, PurchaseTrans, ProductSaleInformation |
| pos_master | local | 60 min | Products, Batches, SalesRep, SupplierProductMatch |
| housekeeping | local | 6 h | Purge acked queue rows (30 d), audit rows (90 d), logs (30 d) |

Each job backs off on failure: 30 s doubling to a 15-minute maximum, with ±20 % jitter. An authentication failure goes straight to the maximum backoff.

## 7. Table synchronisation list
**POS (Shopaid on DESKTOP-CLG2ECP) → OrderNMC:**
- Products, Batches, SalesRep, SupplierProductMatch: full read, change-only MERGE.
- ProductSaleInformation, PurchaseTrans: by ID watermark taken from the destination.
- SaleInformation: PSI window − 1000.
- ProductTrans: 4-month window.

The source queries are copied verbatim from VB `CentralSyncHelper`. MERGE uses the destination primary key, staging is in `#temp`, and each batch is its own transaction.

**HO → OrderNMC:** OrderManagement (+ archive to OrderManagementBackup), OrderHeaderDetails.

**OrderNMC → HO:** `nmv_change_queue`, which captures changes to OrderQty, OrQty, Qtycheck, Remarks, OrSupplier, OrSupplierCode and Status.

**Untouched:** Users, stores, SupplierStock, SupplierExcelMapping, SupplierproductRack, OrderPurchaseTrans, PurchaseTrans4Order, TAX, OrderSuppliers (see above).

## 8. Order flow
1. `GET orders/pending`.
2. Validate: store, header, every line (types, status 0/2, product type and name, quantities), duplicate products, line count, `lines_sha256`.
3. Idempotency check in `nmv_order_inbox`: the same version and hash means re-ack only; the same version with a different hash is `ID_CONFLICT`; a legacy id collision is `ID_CONFLICT`.
4. Replace safety: **defer** while user edits are un-acknowledged or a user edit happened within the last 20 minutes. Amendments are refused once user edits exist.
5. Fill LastSaleBillNo / LastGRN from the POS (the same queries VB uses) if HO did not send them.
6. **One serializable transaction**:
   - archive the current rows to `OrderManagementBackup` (positional, PK-guarded)
   - delete the old order
   - bulk insert the new lines (`Status='0'`, `Qtycheck=0`, `OrgOrderQty`, `StoreCode=10`)
   - insert the `OrderHeaderDetails` row
   - verify the line count and that there are no duplicate ProductCodes
   - write the inbox row (APPLIED)
7. `POST orders/{id}/ack`. The acknowledgement counts only if HO echoes the order id, version and state; otherwise it is retried.

## 9. Result flow
1. A VB edit hits `OrderManagement` and the trigger appends a row to `nmv_change_queue` in the same transaction. It records before/after values, login, host, app and time.
2. The agent sends the queue head (≤200 rows, in change_id order) to `POST order-results`. The `batch_id` is deterministic (epoch + ids), so retries reuse it.
3. The response is validated: batch id echoed, items hash echoed, and every id accounted for exactly once.
4. Accepted and duplicate ids become ACKED. Final rejections become REJECTED and are kept. Retryable rejections stay PENDING.

Internet down or HO errors leave everything PENDING. The VB app is never affected.

## 10. Test results (all executed 2026-10-08; test DB dropped afterwards)

### Trigger (`tests\trigger_tests.sql`, on a schema-only DB loaded with the real 586-line NMV order): 15/15 PASS
- Qty Check edit captured, and the VB row count is unchanged.
- No-op re-save and untracked columns are not queued.
- Supplier assign and un-assign are captured, with NULL-safe comparison.
- The Escape-key zero is captured.
- The multi-row Export update produces one row per changed row (217/217).
- Agent session and unmanaged store are not queued.
- VB `INSERT OMB SELECT * FROM OM` still works.
- An agent delete is allowed.
- **A legacy Process Order delete is blocked and the order stays intact.**
- An unmanaged store delete is allowed as before.

### End-to-end agent ↔ HO stub (`tests\run_ho_tests.ps1`): 44/44 PASS
Covered:
- enrollment, including a wrong code
- DPAPI secrets
- order download appears in OrderManagement and is visible to the VB Qty Check query; previous real order archived (586); header from POS
- duplicate download
- quantity edit, remarks and supplier assignment uploaded with before/after values
- duplicate upload
- Internet disconnect and reconnect
- lost response after HO commit
- partial batch
- malformed acknowledgement
- wrong store in a response
- invalid authentication
- corrupted payload (hash)
- amendment refused after edits
- deferral and later apply
- wrong store code in an order
- heartbeat and `--verify`
- no secrets in logs

### POS sync (real Shopaid → test DB)
- Master tables: 46,512 + 14,378 + 13 + 7,641 rows in 9 s; the second run changed 0 rows.
- Incremental bootstrap: about 1.81M rows in 114 s, in 5,000-row batches; the re-run moved only new rows.

### VB guards (`tests\vb_guard_tests.ps1`, the built exe loaded by reflection): 11/11 PASS
- NMV is managed; Web Export is off and can be switched back on.
- Another store is unmanaged.
- A database without the integration table is unmanaged.
- When the check itself fails, the store is treated as managed (fail-safe).
- The health check against the real instance ran **no** destructive SQL; live OrderNMC stayed ONLINE/MULTI_USER.
- The `sa` login is gone from the source.

### Settings logic
- HTTP is refused without the explicit flag.
- The HO link round-trips through save, and a `.bak` is kept.
- A non-NMV store is refused.

### Live
The schema was installed; `--verify` against live `OrderNMC` passes.

### Not executed here
These need a person at the PC or the real HO endpoint:
- clicking through the VB GUI (login, product search, panels, Qty Check, export)
- a Windows reboot test with the service installed
- a run against the real HO

## 11. Rollback
| Component | Command | Effect |
|---|---|---|
| VB exe | `install\deploy_vb_build.ps1 -Target <folder> -Rollback` | Restores the backed-up exe |
| VB source | Copy `rollback\vb_original\*.orig` back over `Form1.vb` / `SQL_Connection_Module.vb` | Original source restored |
| Service | `install\uninstall_service.ps1 [-RemoveData]` | Service removed; data kept unless `-RemoveData` |
| Database | `sqlcmd -S DESKTOP-2\SQLEXPRESSORDER -E -v DB=OrderNMC FORCE=0 -i sql\001_nmv_integration_rollback.sql` | Drops the trigger first, so VB behaves exactly as before. Drops the `nmv_*` tables only when nothing is un-acknowledged (or with `FORCE=1`) |

## 12. Known limitations
1. **HO has not implemented the contract.** Order pull and result push are tested only against the stub. HO also needs an enrollment flow and must issue the code.
2. **The HO link is plain HTTP.** The device token is visible on the wire. HMAC signing and timestamps prevent tampering and replays older than 5 minutes, but not eavesdropping. Switch to HTTPS in the Settings window once HO supports it.
3. **No VB user name is recorded.** The VB app writes no user to the database; the trigger records the login (`sa`), host, app and time. Recording the user would need a small VB change that sets `CONTEXT_INFO` at login.
4. **One working order per store.** `OrderManagement` has no key, and every VB UPDATE identifies rows by `productcode + storename` only. The agent guarantees one row per product. A user editing an old grid when a new order lands is prevented only by the deferral rules (pending edits or 20-minute quiet period), not by the VB code.
5. **Inherited POS sync behaviour.** Some VB Sync semantics are kept as they were:
   - PSI and PurchaseTrans are ID-watermarked, so later edits to old POS rows are not re-read.
   - Batches only include `Stock>0`.
   - `OrderPurchaseTrans`, `PurchaseTrans4Order` and `SupplierproductRack` have no known source and are untouched.
6. **The delete-guard can surface an error in old builds.** Older VB builds that run Process Order for NMV will now show a SQL error, and may leave a copy of the current order in `OrderManagementBackup` (VB step 1 runs before the blocked delete). Deploy the guarded build to avoid this.
7. **Auto-repair is now opt-in for all installs.** That is a deliberate safety change.
8. **SQL Server 2014 Express limits:** a 10 GB data cap (currently 3.5 GB allocated, 0.6 GB used) and no SQL Agent. All scheduling lives in the service.
9. **No GUI test.** The VB GUI was not exercised interactively; its SQL statements were replayed exactly and its guard functions were invoked from the built assembly.
