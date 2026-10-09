# NMV Store Integration — Design (pre-implementation deliverables 1–10)

Store: **NMV** (stores.storecode = 10) · PC: `DESKTOP-2` · Local DB: `DESKTOP-2\SQLEXPRESSORDER` / `OrderNMC` (SQL Server 2014 Express, compat 120, collation `Latin1_General_CI_AI`) · POS: `DESKTOP-CLG2ECP` / `Shopaid`.

Everything below was verified from source code (`D:\VBDOTNET\OrderManagement\OrderManagement\*.vb`) and from read-only metadata of the live `OrderNMC`. Nothing is inferred from file names.

## Decisions taken (user, 2026-10-08)

| Topic | Decision |
|---|---|
| HO contract | Drafted here (`02_HO_API_Contract.md`); HO implements. Order pull/result push ship **disabled** until HO confirms. |
| Master/sales/purchase/stock data | Sourced from the **local POS over the store LAN** (as the VB Sync button does today). Not pulled back from HO. Works offline. |
| Agent technology | Stand-alone **.NET 4.x C# Windows service** (`NMVSyncAgent`). Runtime/compiler already on the PC. The existing `NexoraStoreAgent` (compiled, no source; uploads POS data to HO) is left untouched. |
| Live changes allowed | VB safety guards; additive change tracking in `OrderNMC`. |

## Facts that shaped the design

* The NMV VB app **already** runs against a local DB (`OrderNMC`, registry `HKCU\Software\OrderDotNetApp\Config`). No new database is needed; the integration is **additive** to it.
* `OrderManagement` has **no primary key**; `Status` is **nvarchar(200)** holding `'0'|'1'|'2'`; `ProductCode`/`StoreCode` are **float**.
* `OrderManagementBackup` PK = `(StoreName, OrderId, ProductCode)`; it is filled by `INSERT INTO OrderManagementBackup SELECT * FROM OrderManagement` (positional, 36 columns each, two columns named differently: `LastReceivedDate`→`LastPurchaseDate`, `MaxSaleQty`→`MaxDaySales`). **Therefore no column may be added to `OrderManagement`.**
* `OrderHeaderDetails` PK = `OrderId` only.
* No triggers existed. `dbo.splitstring(@input, @delimiter)` is a multi-statement TVF returning `Value nvarchar(max)` (SQL is case-insensitive, VB calls `dbo.SplitString`).
* `SqlBulkCopy` (used by VB Process Order) does **not** fire triggers (no `FireTriggers` option).
* The existing HO (`http://122.252.246.181:8443`) is **plain HTTP**. Per instruction (2026-10-08) this link is configured with the explicit `allow_insecure_http` override, which is warned about on every start and in the Settings window. The link is editable later in the Settings window (`NMVSyncAgent.exe --settings`), so HTTPS can be adopted without a rebuild.

---

## 1. VB.NET table dependency matrix (runtime-reachable code only)

S = SELECT, I = INSERT/bulk, U = UPDATE, D = DELETE, M = MERGE. "Dead" = compiled but never invoked.

| Table / object | S | I | U | D | M | Screens / functions | Need | Source today | Sync direction (new) |
|---|---|---|---|---|---|---|---|---|---|
| Users | ✔ | | | | | LoginForm | Required | local admin | none (local) |
| stores | ✔ | | | | | store picker, storeheader.json | Required | local admin | none (local) |
| **OrderManagement** | ✔ | ✔ | ✔ | ✔ | | Process Order, Qty Check, Pending Order, Auto Pur UpDate, Order Based Supplier Stock, Supplier Order Details, Export, Web Export, Compare*, details panel summary (dead) | **Core** | VB Process Order | **HO → local** (orders); **local → HO** (results) |
| **OrderManagementBackup** | ✔ | ✔ | | | | Process Order (archive), order-details panel, Compare*, LoadOrderID | **Core** | VB | local only (agent archives on replace) |
| **OrderHeaderDetails** | ✔ | ✔ | | | | Process Order header, Excel order no, Integrate, LoadOrderIDSupplier | **Core** | VB | **HO → local** (with order) |
| OrderSuppliers | ✔ | | | | ✔ | supplier search (`UnifiedSupplierCODE`), purchase details (LocalDB), Sync target of POS `Suppliers` | Required (assignment) | POS via VB Sync | **POS → local** |
| OrderPurchaseTrans | ✔ | | | | | Auto Pur UpDate | Optional feature | **not written by any VB code** (external) | untouched |
| splitstring (TVF) | ✔ | | | | | Auto Pur UpDate, Supplier Order Details | Required for those | existing | untouched |
| Products | ✔ | | | | ✔ | generation CTE (LocalDB), Integrate/LoadOrderData | Required | POS via VB Sync | **POS → local** |
| ProductSaleInformation | ✔ | | | | ✔ | generation, sales-details panel | Required (panel) | POS | **POS → local** (incremental by ID) |
| SaleInformation | ✔ | | | | ✔ | sales-details panel | Required (panel) | POS | **POS → local** |
| SalesRep | ✔ | | | | ✔ | sales-details panel join | Required (panel) | POS | **POS → local** |
| ProductTrans | ✔ | | | | ✔ | chart, generation | Required (chart) | POS | **POS → local** (4-month window) |
| PurchaseTrans | ✔ | | | | ✔ | purchase-details panel | Required (panel) | POS | **POS → local** (incremental by ID) |
| Batches | | | | | ✔ | Sync only (Access DB export) | Optional | POS | **POS → local** |
| SupplierProductMatch | ✔ | | | | ✔ | Order Based Supplier Stock | Optional feature | POS | **POS → local** |
| SupplierStock | ✔ | ✔ | ✔ | ✔ | | Supplier Stock import, Order Based Supplier Stock, Export | Optional | Excel import (local) | local only |
| SupplierExcelMapping | ✔ | ✔ | ✔ | | | Supplier Excel Mapping | Optional | local | local only |
| SupplierproductRack | ✔ | | | | | Supplier Invoice | Optional | external | untouched |
| PurchaseTrans4Order | ✔ | | ✔ | | | Integrate Order and Purchase | Optional | **not written by VB** (external) | untouched |
| Suppliers | ✔ | | | | | purchase-details panel (RemoteDB mode only, on POS) | Optional | POS | n/a |
| TAX | | | | | | Access DB export only (sync has TAX query but not in Sync list) | Optional | — | not synced (unchanged) |
| ErrorLog, SyncStatus, usp_SmartSyncMerge | | | | | | dead code | Not required | — | — |
| CentralOrderHeader/Detail/Snapshot, OrderManagementHO | — | — | — | — | — | **not referenced anywhere** | **Excluded** | — | — |
| WebOrderStatus | | | | | | referenced only by `webapp old\app.py` (Python prototype) | **Excluded** | — | — |

POS (source) tables read by VB: `ProductSaleInformation` (last `C%` bill), `Purchasetrans` (last `IV` GRN) for the order header, plus the 9 Sync tables.

## 2. Exact column contract (live `OrderNMC`)

### OrderManagement (no PK; 36 columns, order matters for the backup copy)

| # | Column | Type | Null | Written by | Read by |
|---|---|---|---|---|---|
|1|ProductCode|float|Y|gen|all grids, every UPDATE WHERE|
|2|ProductName|nvarchar(200)|Y|gen|grids, Excel, JSON|
|3|TotalStock|float|Y|gen|grids, Compare|
|4|SaleUnit|float|Y|gen|grids ("Pack"), Excel|
|5|PurchasePrice|float|Y|gen|—|
|6|MRP|float|Y|gen|grids, Excel|
|7|SubLocation|nvarchar(200)|Y|gen|—|
|8|UnitDescription|nvarchar(200)|Y|gen|grids|
|9|LastReceivedDate|datetime|Y|gen|grids|
|10|LastSaleDate|datetime|Y|gen|grids|
|11|CMS|float|Y|— (never written)|—|
|12|LMS|float|Y|—|—|
|13|SLSQty|float|Y|gen|grids|
|14|WantedDate|datetime|Y|gen|header OrderDateTime|
|15|WantedType|nvarchar(200)|Y|gen, Compare|filter combo|
|16|Status|nvarchar(200)|Y|gen `'0'`, Additional `'2'`, assign `'1'`, Compare `'2'`/`'0'`|every filter|
|17|MaxSaleQty|float|Y|gen|grids|
|18|OrderQty|float|Y|gen, **Qty Check**, Compare|grids (editable)|
|19|OrgOrderQty|float|Y|gen|details panel, Compare|
|20|OrQty|float|Y|**assignment**, Compare|details|
|21|OrSupplier|nvarchar(200)|Y|**assignment**|details, Compare|
|22|OrSupplierCode|nvarchar(200)|Y|**assignment**|Supplier Order Details|
|23|LastGRN|float|Y|—|—|
|24|LastGRNQTY|float|Y|—|—|
|25|ProductType|float|Y|gen|—|
|26|ProductTypeName|nvarchar(200)|Y|gen `'Pharma'`/`'Non Pharma'`|filter (exact match)|
|27|Remarks|nvarchar(200)|Y|**Qty Check**, Compare, Additional|grids|
|28|OrderId|bigint|Y|gen|JSON, Compare|
|29|MinQty|float|Y|gen|—|
|30|MaxQty|float|Y|gen|—|
|31|Frequence|float|Y|gen|—|
|32|StoreName|nvarchar(200)|Y|gen|every filter|
|33|StoreCode|float|Y|gen|JSON|
|34|Transactiondate|datetime|Y|gen|grids|
|35|Qtycheck|int|Y, default 0|**Qty Check**|Qty Check / Pending filter|
|36|Free|int|Y|— (selected, never persisted)|Qty Check grid|

`OrderManagementBackup`: same 36 positions; NOT NULL on ProductCode, OrderId, StoreName, Transactiondate (default getdate()), Qtycheck (default 10).

### OrderHeaderDetails
`StoreName varchar(50)`, `OrderId bigint NOT NULL PK`, `OrderNo int`, `OrderDateTime datetime`, `LastSaleBillNo varchar(50)`, `LastBillDateTime datetime`, `LastGRN bigint`, `MinDays int`, `MaxDays int`.

### Status codes (verified in code)
`Status`: `'0'` open · `'1'` assigned to supplier (ordered) · `'2'` excluded (Additional Row / already ordered). `Qtycheck`: `0` not reviewed · `1` reviewed.
Remark literals written by VB: `Don't Want to Order`, `Don't want to Order`, `OrderQty Changed N Add`, `OrderQty Changed N Less`, `No Changes in OrderQty`, `No Changes In OrderQty`, `Additional`, `After Order Sold`, `Compare Order with <id>`, `Compare Supplier <code> with Order ID: <id>`. Supplier literals: `OrSupplier='Pending Order'`, `OrSupplierCode='pending'`.

### Keys the application relies on
* All VB `UPDATE ordermanagement` statements identify a row by **`productcode + storename`** (+ status). They never use OrderId. ⇒ at most one OrderManagement row per (StoreName, ProductCode) is the working assumption. The agent enforces this on every order it applies.
* Backup uniqueness: `(StoreName, OrderId, ProductCode)`.

## 3. Read/write map (who writes what after integration)

| Data | Writer | Reader |
|---|---|---|
| OrderManagement rows (new order) | **Agent** (from HO) | VB |
| OrderQty / Remarks / Qtycheck | VB (Qty Check) | trigger → queue → Agent → HO |
| OrQty / OrSupplier / OrSupplierCode / Status | VB (assignment, Export, Compare) | trigger → queue → Agent → HO |
| OrderManagementBackup | Agent (archive on replace); VB Process Order (now blocked for NMV) | VB |
| OrderHeaderDetails | Agent (from HO) | VB |
| POS copies (Products … SupplierProductMatch) | Agent (POS → local) | VB |
| nmv_* integration tables | Agent + trigger | Agent, operators |

## 4. Sync direction map

```
POS Shopaid (LAN) ──read──► Agent ──MERGE──► OrderNMC: Products, ProductSaleInformation, SaleInformation,
                                            ProductTrans, PurchaseTrans, SalesRep, OrderSuppliers, Batches,
                                            SupplierProductMatch                     [works offline]
HO (HTTPS) ──orders──► Agent ──txn──► OrderManagement (+archive to OrderManagementBackup) + OrderHeaderDetails
VB edits ──► OrderManagement ──trigger──► nmv_change_queue ──Agent──► HO (HTTPS) ──ack──► queue ACKED
```
Not synced: Users, stores, SupplierStock, SupplierExcelMapping, SupplierproductRack, OrderPurchaseTrans, PurchaseTrans4Order, TAX (unchanged from today).

## 5. Local DB schema plan

No new database. Additive objects only (`sql/001_nmv_integration_install.sql`):

| Object | Purpose |
|---|---|
| `nmv_integration_store` | Which stores are integration-managed (seeded `NMV`). Read by the VB guards. |
| `nmv_change_queue` | Persistent outbox of every tracked OrderManagement change (before/after values, host, login, time, sync state, attempts, backoff). |
| `nmv_order_inbox` | One row per HO order received: version, payload hash, line count, apply/ack state ⇒ idempotency. |
| `nmv_sync_state` | Watermarks, queue epoch, last-run timestamps. |
| `nmv_sync_audit` | Per-run audit (category, table, rows examined/changed, outcome, duration). |
| `trg_nmv_OrderManagement_track` | AFTER INSERT/UPDATE/DELETE trigger on OrderManagement. |

No existing column, type, nullability, key or status code is changed. Nothing is added to `OrderManagement`.

## 6. Change tracking design

* **Trigger** on `OrderManagement` (the only table users edit that HO needs):
  * `SET NOCOUNT ON` → VB `ExecuteNonQuery` row counts are unchanged.
  * Skips sessions whose `CONTEXT_INFO` starts with `NMV_AGENT` (the agent's own writes ⇒ no echo, no recursion; the trigger never writes OrderManagement).
  * Captures only stores present in `nmv_integration_store` with `IsManaged = 1`.
  * UPDATE: quick exit unless one of the 7 tracked columns appears in the SET list; then a row-level `EXCEPT` comparison (NULL-safe) so only real value changes are queued.
  * Set-based single INSERT … SELECT ⇒ one statement regardless of rows touched (Compare/Export update many rows).
  * Matching of inserted/deleted rows: `(StoreName, OrderId, ProductCode)` (OrderManagement has no key; the agent guarantees uniqueness for HO orders).
  * VB Process Order bulk insert does not fire triggers (and is blocked for NMV); its DELETE would be captured as `D` rows — harmless, and the button is guarded.
* **Queue semantics**: append-only; each row carries before/after for OrderQty, OrQty, Qtycheck, Remarks, OrSupplier, OrSupplierCode, Status. HO applies in `change_id` order. Rows are never deleted until ACKED and older than the retention period (default 30 days). REJECTED rows are kept indefinitely for operator review.
* **Idempotency key** sent to HO: `queue_epoch` (GUID created at install, stored in `nmv_sync_state`) + `change_id` ⇒ safe even after a DB restore resets identity values.
* **User identity**: the VB app writes no user to the DB; the trigger records `SUSER_SNAME()` (currently `sa`), `HOST_NAME()`, `APP_NAME()` and time. Capturing the VB login user would need a VB change to set `CONTEXT_INFO` — deferred (known limitation).

## 7. Sync Agent architecture

`NMVSyncAgent.exe` (.NET Framework 4.x, C#), Windows service, runs as virtual account `NT SERVICE\NMVSyncAgent` (no password).

| Component | Responsibility |
|---|---|
| Config | `%ProgramData%\NMVSyncAgent\agent.json` (no secrets) |
| SecretStore | DPAPI (LocalMachine + entropy) file `secrets.dat`, ACL = SYSTEM, Administrators, service SID |
| Log | daily files in `%ProgramData%\NMVSyncAgent\logs`, redaction, retention |
| Scheduler | independent jobs with own interval, jitter, single-flight, failure backoff |
| PosSync | POS → local, same queries & merge keys as VB `CentralSyncHelper`, but `#temp` staging, per-batch transaction, change-only MERGE, surfaced errors, audit rows |
| OrderPull | HO → local; validate (store identity, line hash, counts, duplicates, types); apply in one transaction; ack HO |
| ResultPush | queue → HO in batches; validate per-item ack; partial retry; backoff; DEAD after max attempts is **not** used — rejected-retryable keep retrying, non-retryable become REJECTED (kept) |
| Heartbeat | queue depth, last runs, version |
| CLI | `--console`, `--once <job>`, `--set-secret <name>` (stdin), `--enroll` (stdin code), `--verify`, `--status` |

Job categories and default cadence (all configurable): `results_push` 30 s · `orders_pull` 60 s · `heartbeat` 5 min · `pos_incremental` 15 min (ProductSaleInformation, SaleInformation, PurchaseTrans, ProductTrans) · `pos_master` 60 min (Products, Batches, OrderSuppliers, SalesRep, SupplierProductMatch) · `housekeeping` 6 h.

## 8. API contract expected from HO
See `02_HO_API_Contract.md`.

## 9. Security model
* Agent → HO only, outbound **HTTPS (TLS 1.2+)**; HTTP refused unless `allow_insecure_http` is explicitly set (logged as WARNING on every start). SQL Server is never exposed; no SQL credential ever leaves the PC.
* Device identity: one-time enrollment code → HO issues `device_token` + `device_secret`. Every request: `Authorization: Bearer`, `X-Nexora-Store-Id`, `X-Nexora-Store-Code: NMV`, `X-Nexora-Timestamp`, `X-Nexora-Signature` = HMAC-SHA256 over timestamp, method, path, body hash.
* The agent only operates as NMV: config store code is fixed, every HO response must echo `store_code=NMV` and the configured `store_id`; anything else is rejected and logged.
* Secrets only in DPAPI store; never in config, source or logs (logger redacts tokens/passwords/connection-string passwords).
* Local SQL: agent uses Windows auth as its virtual service account with `db_datareader`, `db_datawriter` and `EXECUTE` on `OrderNMC` only — not `sa`.
* Static IP: may be used by HO for allow-listing; not relied upon.

## 10. Failure / retry model

| Failure | Behaviour |
|---|---|
| Internet/HO down | Push/pull jobs fail fast (timeouts 15 s connect / 60 s read), exponential backoff with jitter (30 s → max 15 min). VB unaffected; edits accumulate in `nmv_change_queue`. |
| HO succeeded but response lost | Re-send same items with same idempotency keys; HO must answer `duplicate` ⇒ marked ACKED. |
| Partial batch | Per-item results; only acknowledged ids are marked ACKED; others retried; non-retryable → REJECTED. Malformed/unaccounted response ⇒ whole batch retried. |
| Corrupted order payload | Hash / count / type / store mismatch ⇒ not applied, inbox REJECTED, negative ack to HO. |
| Same order downloaded twice | Inbox hit with same hash ⇒ no-op, re-ack. Same id with different hash ⇒ REJECTED (conflict), nothing changed. |
| New order while user still editing | Deferred while queue has un-acked items for the current order or a user change was captured within `order_replace_quiet_minutes` (default 20). |
| Apply fails midway | Single SQL transaction with `XACT_ABORT ON` ⇒ full rollback; retried next cycle. |
| POS unreachable | POS jobs fail and back off; local data stays as of last success. |
| Auth failure (401/403) | No retry storm: backoff to max, logged as AUTH error. |
| Agent crash / reboot | Service recovery restarts it (3 restarts, 60 s); state is entirely in SQL, so jobs resume. |
