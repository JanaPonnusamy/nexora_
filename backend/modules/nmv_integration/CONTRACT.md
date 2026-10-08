# NMV Store Integration — HO-side contract

Integration boundary between Nexora HO / OrderNMC and the **NMV** store, whose
existing VB.NET OrderManagement app runs against an NMV-local SQL database that
HO can **never** reach directly over the Internet.

```
Nexora Legacy Order ─► OrderNMC (central) ─► NMV Integration API (HTTPS)
                                                     ▲   │
                                       outbound POST │   │ outbound GET
                                                     │   ▼
                                               NMV Sync Agent
                                                     │
                                               NMV Local SQL ◄─► VB.NET OrderManagement
```

The NMV agent **always initiates** the connection (outbound HTTPS). HO never
dials into NMV. TCP 1433 is never exposed. This module is purely a transport +
state boundary; **order generation stays with Legacy Order** (no second order
system).

> Ground truth for "what the VB.NET app actually uses" is the verbatim Python
> port of the legacy app already in this repo —
> [sync_engine.py](sync_engine.py) (`CentralSyncHelper.vb`),
> [order_process.py](order_process.py) (`Form1.ProcessOrder`), and
> [repository.py](repository.py) (the Order Workspace queries). Columns/keys
> below are taken from those ports, not guessed.

---

## A. NMV dependency matrix

Legend — **Dir**: `UP` = NMV→HO (agent POST), `DOWN` = HO→NMV (agent GET),
`BI` = bidirectional control. **R/O**: Required / Optional. **Freq**: C=every
cycle, O=order-time, D=on-demand.

### A.1 Uplink — NMV POS data → central OrderNMC (replaces the legacy direct branch pull)

These are exactly `sync_engine.TABLE_PLAN`. Source table at NMV → destination in
OrderNMC. The agent sends JSON rows; HO lands them with the **same MERGE keys**
as the direct pull (`sync_engine.merge_keys`), stamped `StoreName='NMV'`.

| Source table | Dest (OrderNMC) | Dir | R/O | Incremental watermark | Merge key (StoreName-scoped) | Freq | Notes |
|---|---|---|---|---|---|---|---|
| Products | Products | UP | Req | snapshot (`isActive=1`) | ProductCode | C | full active catalogue |
| SaleInformation | SaleInformation | UP | Req | `maxPSI_ID − 1000` | BillDate, BNumber | C | header; sent *after* PSI (see sync_engine note) |
| ProductTrans | ProductTrans | UP | Req | snapshot (last 4 months) | ProductCode, MonthOfStatistics | C | monthly rollup |
| PurchaseTrans | PurchaseTrans | UP | Req | `MAX(ID)` | ID | C | GRN/purchase lines |
| ProductSaleInformation | ProductSaleInformation | UP | Req | `MAX(ID)` (TransactionValidity=0) | ID | C | sale lines; drives SaleInformation watermark |
| SalesRep | SalesRep | UP | Req | snapshot (`isactive=1`) | Salesmancode | C | |
| Suppliers | **OrderSuppliers** | UP | Req | snapshot (`IsActive=1`) | suppliercode | C | lands in OrderSuppliers, not Suppliers |
| Batches | Batches | UP | Req | snapshot (`Stock>0`), full-replace | ProductCode, BatchCode | C | sold-out batches zeroed first (legacy behaviour) |
| SupplierProductMatch | SupplierProductMatch | UP | Opt | snapshot | suppliercode, supplierproductcode | C | ho_supplier_code stamped after merge |

### A.2 Uplink — processed order results → OrderManagement

The VB.NET user edits the delivered order locally; the agent sends only the
changed **result columns** back. Identity = `StoreName + OrderId + ProductCode`.

| Column | Dir | R/O | Written where | Notes |
|---|---|---|---|---|
| OrderQty | UP | Req | OrderManagement | qty-check / manual edit |
| OrQty | UP | Req | OrderManagement | ordered qty at assignment |
| QtyCheck | UP | Req | OrderManagement | 0/1 review flag |
| Remarks | UP | Opt | OrderManagement | review remark text |
| OrSupplier | UP | Req | OrderManagement | assigned supplier name |
| OrSupplierCode | UP | Req | OrderManagement | assigned supplier code |
| Status | UP | Req | OrderManagement | 0 open / 1 assigned / 2 processed |

No other OrderManagement column is writable from NMV. Rows for any other
`StoreName` are unreachable by this path.

### A.3 Downlink — order + workflow context → NMV local SQL

What the VB.NET Order Workspace reads locally (from `repository.py`). HO is the
producer; the agent pulls and writes these into NMV-local SQL.

| Entity (OrderNMC) | Dir | R/O | Watermark | Used by VB screen |
|---|---|---|---|---|
| OrderManagement (StoreName='NMV') | DOWN | Req | `OrderId` | the order grid |
| OrderHeaderDetails | DOWN | Req | `OrderId` | order header/audit |
| OrderManagementBackup | DOWN | Opt | `OrderId` | previous-order compare / history |
| OrderSuppliers | DOWN | Req | content hash | supplier search list |
| SupplierStock | DOWN | Opt | content hash | "Live Stock" supplier mode |
| SupplierProductMatch (ho_supplier_code) | DOWN | Opt | content hash | supplier-product match |

### A.4 Control / metadata (bidirectional)

| Entity | Dir | Purpose |
|---|---|---|
| manifest | DOWN | per-table HO watermarks + current OrderId + config version |
| ack | UP | advance a downlink watermark only after the agent confirms receipt |
| message receipt | UP→state | inbound idempotency token (dedupe/replay) |
| sync audit | state | per-message correlation, counts, timing, outcome |

### A.5 Tables explicitly **NOT** included (unverified)

`CentralOrderHeader`, `CentralOrderDetail`, `CentralOrderSnapshot`,
`OrderManagementHO`, `WebOrderStatus`, `PurchaseTrans4Order`, `SplitString`,
`OrderPurchaseTrans`, `SupplierExcelMapping`, `SupplierProductRack`, `TAX`,
`Users`, `stores`.

Reason: none appear in the authoritative VB.NET ports as data the order
workflow reads or writes over the sync boundary. `SplitString` is a TVF (code,
not data). `TAX` has never synced historically (documented in sync_engine).
These stay out until the real NMV VB.NET source confirms a need.

---

## B. Table-by-table sync contract

* **Uplink POS tables (A.1):** incremental by the watermark column above. The
  agent asks `manifest` for HO's current watermark per table, selects local rows
  beyond it, and POSTs them in bounded batches. HO MERGEs via
  `sync_engine.build_merge_sql` (reused verbatim — no second merge dialect).
  Snapshot tables are replace-style exactly as the legacy pull did them.
* **Order results (A.2):** set-based `UPDATE ... WHERE StoreName='NMV' AND
  OrderId=? AND ProductCode=?` restricted to the 7 whitelisted columns, with an
  optimistic `expected_status` guard to avoid clobbering a concurrent edit.
* **Downlink (A.3):** the agent pulls by `OrderId` (orders/header/backup) or by
  content hash (supplier reference). A watermark is advanced **only** on an
  explicit `ack`, so a failed write at NMV safely re-pulls.

---

## C. API contract

All routes are under `/api/nmv-integration/v1/stores/{store_code}` and require a
**device bearer token** (see §E). `store_code` must resolve to a platform store
the calling device is assigned to, else `403`. Phase-1 the only valid code is
`NMV`.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/config` | — | agent polling config + config_version |
| GET | `/manifest` | — | per-table watermarks, current OrderId, server_time |
| GET | `/changes?entity=&since=&cursor=&limit=` | — | one downlink entity page (chunked) + next_cursor |
| GET | `/orders?order_id=` | — | OrderManagement rows for the current (or given) OrderId |
| POST | `/uplink` | `{message_id, table, watermark, rows[]}` | `{applied, merged, skipped_duplicate}` |
| POST | `/order-results` | `{message_id, order_id, results[]}` | `{applied, conflicts[], skipped_duplicate}` |
| POST | `/ack` | `{entity, watermark}` | `{entity, watermark}` |
| GET | `/status` | — | last uplink/downlink watermarks + recent audit |

* Every POST carries a client-generated `message_id` (UUID). HO records it; a
  replay returns the original result with `skipped_duplicate=true` and applies
  nothing. This is both idempotency and write-path replay protection.
* Responses never return another store's rows; all reads are `StoreName='NMV'`.
* No endpoint returns "the whole database" — downlink is entity + page + cursor.

---

## D. Database migration plan

**Additive only**, in OrderNMC (so idempotency records commit in the *same*
transaction as the data they guard). No legacy table is renamed/retyped; no
status semantics change. File: [sql/0001_nmv_integration.sql](sql/0001_nmv_integration.sql),
applied by an idempotent `ensure_schema()` (agent_ops pattern).

New tables (all `dbo`, prefixed `nmv_`):
* `nmv_sync_watermark(store_name, entity, strategy, watermark_num, watermark_str, updated_at)` — PK (store_name, entity).
* `nmv_sync_message(message_id, store_name, direction, kind, received_at, status, rows_in, rows_applied, error, response_json)` — PK message_id; dedupe/idempotency ledger.
* `nmv_sync_audit(audit_id, store_name, device_id, message_id, entity, direction, rows, started_at, ended_at, status, detail)` — correlation/audit.

Rollback: `DROP TABLE dbo.nmv_sync_audit; dbo.nmv_sync_message; dbo.nmv_sync_watermark;`
Nothing else is touched, so rollback is clean and leaves OrderNMC exactly as before.

---

## E. Security model

* **Transport:** HTTPS only; agent dials out; 1433 never exposed.
* **Identity:** reuse the existing **device identity** module — the NMV agent is
  a registered device (Ed25519 keypair; HO stores only the public PEM) that
  obtains a short-lived device bearer token by signing a
  `device_id.timestamp.nonce` challenge (`±300s` skew bound → replay-bounded).
* **Authorization:** `get_nmv_device` requires `token_kind='device'`, an active
  registration, and that the device is assigned (in `device_store_assignments`)
  to the platform store whose `store_code` == the path `store_code`. The client
  **cannot** widen scope by changing the path — it is validated server-side
  against the token's assigned stores.
* **Store isolation:** every query is hard-scoped to `StoreName='NMV'`. There is
  no code path that accepts a client-supplied StoreName for a read/write.
* **Write replay:** `message_id` dedupe (§C).
* **Secrets:** no plaintext secrets stored or logged; tokens/keys never audited
  (audit records counts + correlation ids only).

## F. Failure / retry model

* All POSTs are idempotent by `message_id`; a network failure after HO committed
  still returns the same result on retry and applies nothing twice.
* Downlink watermarks advance **only** on `ack` → a dropped page is simply
  re-pulled; no data loss.
* Uplink MERGE is per-batch; a failed batch is reported, not silently skipped,
  and the HO watermark is only moved forward past rows that actually merged.
* Offline: the agent resumes from its last acked watermark; partial batches are
  safe to resend.

---

## Isolation from the existing 5 stores (NMA/NMW/NMC/NMG/NMS)

* NMV is **not** added to the legacy direct-pull `dbo.Stores` sync path; HO holds
  no NMV SQL credentials and never calls `get_branch_connection` for NMV.
* This module adds endpoints + 3 additive tables + one `include_router` line. It
  does not modify `legacy_order`, `procurement`, `sync`, or any existing module.
* Existing stores keep their exact sync path and behaviour.

## Still uncertain / follow-up (outside this module)

* **NMV order generation** still runs in Legacy Order. Because HO can't reach
  NMV's branch, it must run in **local mode** against the central copy that this
  module's uplink populates. `order_process.update_order_header_details` reads
  last-sale-bill / last-GRN from the *branch*; for an agent-synced store those
  two reads must come from the central copy (StoreName-scoped). That is a small,
  separate, owner-approved change to `legacy_order` — intentionally **not** made
  here to keep this module isolated.
* Exact NMV-local SQL schema (table/column case, extra columns) should be
  confirmed against the real NMV VB.NET build before first production cutover.
