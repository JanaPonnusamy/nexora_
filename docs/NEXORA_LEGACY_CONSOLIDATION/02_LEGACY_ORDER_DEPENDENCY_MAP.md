# Legacy Order Engine — Dependency Map

Scope: `backend/modules/legacy_order/*`, its frontend (`frontend/src/pages/legacy-order/*`,
`frontend/src/services/legacyOrderService.ts`) and its desktop client surface
(`desktop/supplier-stock-client/src/ProcurementWorkspace.jsx`,
`LegacyOrderGeneration.jsx`, `api/client.js`). Read-only investigation; no files
were modified. Status tags: **VERIFIED** (read the exact code), **PARTIAL**
(read code but did not execute/trace runtime behaviour or DB contents),
**INFERRED** (reasoned from naming/comments/adjacent code, not directly
confirmed), **UNKNOWN** (flagged, not resolved).

Git note: working tree has **uncommitted changes already applied** to
`order_process.py` and `repository.py` (see `git diff`, captured below) — these
are in-progress/completed fixes, not just drafts. They are included in this
map as the current state of the code, with a note on what they changed.

---

## 1. Top-level module inventory

| File | Lines | Role |
|---|---|---|
| `backend/modules/legacy_order/router.py` | 1305 | FastAPI router `/api/legacy-order/*`; all HTTP surface, permission gating, tenant scoping |
| `backend/modules/legacy_order/service.py` | 941 | Job orchestration (sync, order-process, stock-update) on worker threads; store/engine/warning resolution |
| `backend/modules/legacy_order/order_process.py` | 723 | Core LEGACY-engine SQL execution + OrderManagement rewrite (the ported VB `ProcessOrder`) |
| `backend/modules/legacy_order/rulebook_order.py` | 465 | RULEBOOK engine (Procurement `quantity_profile_t`) wired into the same OrderManagement tables; engine/compare-mode settings; Legacy-vs-RuleBook dry-run compare workbook |
| `backend/modules/legacy_order/repository.py` | 2976 | All SQL against OrderNMC/central copy: stock, suppliers, qty-check, pending, auto-assign, skip rules, compare-previous-order, restore, workflow |
| `backend/modules/legacy_order/order_export.py` | 945 | Excel/CSV/XLS/PNG export builder (By Supplier + Pending) |
| `backend/modules/legacy_order/evening_order.py` | 340 | Scheduled "second order" run for a configured store list |
| `backend/modules/legacy_order/supplier_whatsapp.py` | 275 | Per-supplier WhatsApp contact/auto-send config + sent-log |
| `backend/modules/legacy_order/supplier_portal.py` | 155 | Per-supplier web ordering portal URL/login (encrypted password) |
| `backend/modules/legacy_order/supplier_stock_harvest.py` | 142 | Write-only ingestion of a supplier portal's catalog into `SupplierStock` |
| `backend/modules/legacy_order/supplier_match_review.py` | 192 | Matches harvested supplier stock to store products → `SupplierProductMatch` |
| `backend/modules/legacy_order/sync_engine.py` | 583 | Generic branch→central table sync engine used by both Order Process pre-sync and the standalone Sync button |
| `backend/modules/legacy_order/auto_sync.py` | 78 | Background scheduled sync loop |
| `backend/modules/legacy_order/device_sync.py` | 109 | Triggers + waits for an agent-synced store's live device sync |
| `backend/modules/legacy_order/database.py` | 574 | Connection strings, tenant resolution, DB health/recovery |
| `backend/modules/legacy_order/schemas.py` | 260 | Pydantic request/response models |
| `backend/modules/legacy_order/sql/*.sql` | — | Hand-ported VB SQL + migrations |
| `backend/tests/test_legacy_order_warehouse_stock_sync.py` | 137 | New (untracked) tests for the warehouse-stock agent-sync fix |
| `backend/modules/procurement/product_identity.py` | 108 | **Shared boundary file** — `collapse_lines`/`collapse_generated_payload`, imported by `legacy_order.repository` and `legacy_order.order_process` (new, untracked) |
| `backend/modules/procurement/quantity_profile_t.py` | 132 | **Shared boundary file** — the RULEBOOK engine's quantity formula, imported by `legacy_order.rulebook_order` |
| `backend/modules/procurement/abnormal_sales_service.py` | ~190 | **Shared boundary file** — `legacy_abnormal_sales`/`set_dont_consider`, called from `legacy_order.router` |

**VERIFIED** — file list and line counts via `wc -l` / `Read`.

---

## 2. End-to-end execution path (user opens Order Workspace → order exported)

### 2.1 Frontend entry points

- Web: `frontend/src/pages/legacy-order/LegacyOrderPage.tsx` (912 lines, store
  picker + Sync/Order-Process triggers + job polling + evening-order settings)
  and `frontend/src/pages/legacy-order/OrderWorkspacePage.tsx` (889 lines,
  the Qty Check / Pending / Supplier-assign / Export grid), routed via
  `frontend/src/routes/AppRouter.tsx` and listed in
  `frontend/src/components/sidebar/navConfig.ts`. **VERIFIED** (`Read` of
  `OrderWorkspacePage.tsx:1-120`, `Grep` of `AppRouter.tsx`/`navConfig.ts`).
- Desktop (Electron, the one in active owner use per memory
  `keep-legacy-order-workspace-unchanged` / `procurement-electron-workspace`):
  `desktop/supplier-stock-client/src/ProcurementWorkspace.jsx` (2168 lines) and
  `LegacyOrderGeneration.jsx` (789 lines), calling the same backend router
  through `desktop/supplier-stock-client/src/api/client.js` (lines 938–1305
  enumerate every `/api/legacy-order/...` call the desktop client makes —
  **VERIFIED** via `Grep`). The desktop client's call surface matches the web
  `legacyOrderService.ts` 1:1 except it also calls `/order-entry` (PM Order
  Entry screen) which the web service does not wrap.
- `frontend/src/services/legacyOrderService.ts` (314 lines) is the complete web
  API client — every method maps 1:1 to a `router.py` route. **VERIFIED**
  (full file read).

### 2.2 Order generation call chain (the "Order & Process" button)

```
UI (LegacyOrderPage / LegacyOrderGeneration)
  → POST /api/legacy-order/order-process            router.py:294-321
    → service.start_order_process(...)              service.py:365-530
      - resolves store, engine, compare_mode, min/max/recency days
      - WARNING gates (not locks): StaleCurrentOrder (repository.
        require_current_date_order_if_any), QtyCheckConfirmationRequired
        (repository.qty_check_confirmation_count) — single-warning rule
        (service.py:488-515)
      - branches: agent-synced store -> _run_agent_sync_then_order (thread)
                  else               -> _run_sync_then_order (thread)
    → (thread) full branch/platform sync (sync_engine.sync_table per table)
    → _check_checkpoint (last-bill/last-GRN gate, repository.
      check_order_checkpoint)                        service.py:124-139
    → order_process.run_order_process(...)           order_process.py:629-723
      - refresh_warehouse_stock(store, warehouse_source) BEFORE generating
        the order for a non-warehouse store                order_process.py:675-681
      - engine switch: LEGACY -> fetch_source_data() (sql/order_local.sql
        or order_remote.sql or order_warehouse.sql)       order_process.py:693-699
                        RULEBOOK -> rulebook_order.build_order()  order_process.py:688-692
      - insert_data_into_destination(): backup -> delete -> bulk insert ->
        zero 'Additional Row' lines -> set IsOffer -> apply_carried_skips
                                                           order_process.py:205-363
      - update_order_header_details(): stamps OrderHeaderDetails          order_process.py:366-464
    → optional compare-with-previous/-today (service._compare_for_mode)
    → service._push_to_mirrors(store_name)  (OrderNMC mirror, best-effort)
```
**VERIFIED** (read `order_process.py` and `service.py` in full).

### 2.3 Qty Check → Pending → Supplier assignment → Export

```
GET /qty-check/{store}            repository.qty_check_rows          router.py:1091-1096
PATCH /qty-check/{store}/{code}   repository.update_qty_check        router.py:1140-1154
POST /qty-check/{store}/{code}/skip  repository.skip_product         router.py:1157-1176
GET /pending-order/{store}        repository.pending_order_rows      router.py:1132-1137
GET /orders/{store}/by-supplier   repository.orders_by_supplier      router.py:582-589
POST /orders/{store}/auto-assign  repository.auto_assign_apply       router.py:691-706
POST /orders/{store}/{code}/assign repository.assign_supplier        router.py:708-725
POST /orders/{store}/export       order_export.export_order          router.py:913-955
```
**VERIFIED** (router.py read in full, cross-checked against repository.py
function bodies).

---

## 3. Detailed findings per investigation item

### 3.1 Supplier selection and allocation logic — **VERIFIED**

Two paths:

1. **Manual assignment** — `repository.assign_supplier`
   (`repository.py:1586-1631`): toggles `OrderManagement.Status` 0↔1, copies
   `OrderQty` into `OrQty`, stamps `OrSupplier`/`OrSupplierCode`. Status 2
   rows (already processed by a compare) are left untouched.
2. **Auto-assign / "Bulk Assign · Best Margin"** —
   `repository.auto_assign_proposals` + `auto_assign_apply`
   (`repository.py:1728-1845`). For every Pending line (qtycheck=1, status=0,
   orderqty>0), it looks at the product's **last 5 real supplier receipts**
   (`AUTO_ASSIGN_LAST_SUPPLIES = 5`, `InvoiceSeries='IV'`,
   `StockReceived>0`), computes a margin per supply
   (`receipt_margin`, `repository.py:1686-1697`:
   `(MRP - net_unit_cost) / MRP * 100`, `net_unit_cost = ItemCost * received /
   (received + free)`), and picks the supplier with the **best margin among
   its most recent supply, tie-broken by (margin, count of the 5 supplies,
   most recent date)** (`pick_auto_assign_supplier`, `repository.py:1700-1725`).
   Matches memory note "OW Bulk Assign best margin" exactly. Fallback: most
   frequent supplier by purchase-receipt count, then by past
   `OrderManagementBackup` assignment count, filtered to currently-active
   `OrderSuppliers`.
3. **Supplier-stock-based "By Supplier"** mode (`mode='stock'` in
   `orders_by_supplier`) matches candidate products to live `SupplierStock`
   rows via `SupplierProductMatch`, with stock/rack columns — this is how a
   supplier's live catalog stock is surfaced for manual picking
   (`repository.py:1209-1346`, not fully quoted here but read in full).

Tenant scope: every one of these functions takes `store_name` and filters SQL
`WHERE StoreName = ?` — scoped to a single store, consistent with
`_scope_tenant` resolving the store's tenant before the repository call
(`router.py:172-202`).

### 3.2 Product selection and filtering — **VERIFIED**

LEGACY engine (`sql/order_local.sql`, `order_remote.sql`, `order_warehouse.sql`):
eligibility is baked into the CTE `WHERE` clauses:
- `ProductSaleInformation.TransactionValidity = 0`, `Quantity > 0`,
  `SeriesTransID = 1` (retail bill) — warehouse also ORs in
  `SeriesName = 'TO'` (Transfer-Out).
- `ISNULL(DontConsiderInOrder, 0) = 0` — this is the abnormal-sale "do not
  consider" flag written by `abnormal_sales_service.set_dont_consider`
  (shared with the Procurement module; see §4).
- `Products.IsActive = 1`.
- A product only appears in the final result if
  `(maxqty - TotalStock) / SaleUnit > 0 AND minqty > TotalStock AND
  lastsaledate >= LastReceivedDate AND lastsaledate >= (today - recencydays)`
  (the "demand still outstanding, sold more recently than received, sold
  recently enough" triple gate).
- A separate `UNION ALL` branch ("Additional Row") picks up **rare movers**:
  `TotalStock <= 1 AND minqty <= 1 AND Frequence > 1 AND slsqty > 1` and not
  already covered by the main branch — forced into the order at qty 1 for
  manual review, later zeroed by `insert_data_into_destination`'s
  `WantedType = 'Additional Row'` UPDATE (`order_process.py:323-328`).

RULEBOOK engine (`sql/order_rulebook_inputs.sql` + `quantity_profile_t.
evaluate_profile_t`): eligibility is in Python, not SQL — `BLOCKED_SALE_UNIT`
(no/zero `SaleUnit`), `EXCLUDED_DONT_CONSIDER`, `EXCLUDED_NO_SALES`,
`REVIEW_RECENCY` (no sale in the recency window), `SUPPRESSED_NO_SALE_SINCE_
RECEIPT` (sale predates last GRN) — see `quantity_profile_t.py:71-88`.

### 3.3 Order quantity calculation (core formula) — **VERIFIED**

**LEGACY engine** (`sql/order_local.sql`, identical core math in
`order_warehouse.sql` and the older `order_remote.sql`):

```
AvgSalesQty   = CEILING(slsqty / Frequence)                  -- slsqty = 90-day window sum
minqty = MAX( CEILING((slsqty/90.0) * @minday), AvgSalesQty )
maxqty = MAX( CEILING((slsqty/90.0) * @maxday), MaxSalesQtyInBill )
OrderQty =
    CASE WHEN TotalStock = 0 AND (maxqty - TotalStock) <= 0 THEN 1
         WHEN SaleUnit > 0 THEN CEILING((maxqty - TotalStock) / SaleUnit)
         ELSE 0 END
```
`@minday`/`@maxday` default **13/18 days** for retail
(`service.DEFAULT_MIN_DAYS/MAX_DAYS`, `service.py:23-24`) and **32/35 days**
for a warehouse store (`service.WAREHOUSE_MIN_DAYS/MAX_DAYS`, `service.py:
38-39`). The 90-day window (`@ODATA`) is hardcoded
(`order_process.py:651`: `datetime.date.today() - timedelta(days=90)`), not
parameterised per store.

**RULEBOOK engine** (`quantity_profile_t.evaluate_profile_t`,
`quantity_profile_t.py:50-118`), formally:

```
avg_daily = window_qty / window_days                          -- window_days default 90
avg_bill  = window_qty / bill_frequency  (0 if no bills)
gross = MAX(avg_daily * max_days, max_bill_qty, max_day_qty, avg_bill)
        -- first-listed term wins ties: "cover" (avg_daily*max_days) wins over
        -- max_bill/max_day/avg_bill on an exact tie
net   = gross - total_stock - confirmed_pending            -- confirmed_pending always 0 today (PRR-STK-PENDING unresolved, see §3.7)
packs = CEILING(net / sale_unit)
```
with a `RARE_MOVING_MANUAL_REVIEW` carve-out (1 pack, flagged for review) when
`net <= 0` but `stock<=1, min_qty<=1 (legacy floor formula), line_frequency>1,
window_qty>1, and last_sale > last_received`. Parameters
(`window_days/min_days/max_days/recency_days`) come from the Procurement
Rules Registry (`PRR-QTY-WINDOW/MIN-COVER/MAX-COVER/RECENCY`) when the store
is on the platform, else the hardcoded defaults 90/13/18/15
(`rulebook_order.py:44-50, 192-210`).

**Owner-documented target formula** (per `rulebook_order.py:11-22` docstring,
referencing `docs/procurement-workspace-unification/06_PROCUREMENT_RULEBOOK.
md`) matches what is implemented — **VERIFIED** the code matches its own
docstring's stated target; did not independently re-read that external
unification doc (**out of this investigation's scope**, belongs to the other
Procurement-side investigation).

Both engines' **output is written through the same
`insert_data_into_destination` and the same `OrderManagement` table shape**
(`order_process.COLUMN_MAP`, `order_process.py:119-146`), so downstream
Qty Check/Pending/Export/WhatsApp code paths are engine-agnostic — this is the
key fact for consolidation: **the RULEBOOK engine is already a drop-in
alternative calculation inside Legacy Order's own tables**, not a separate
procurement-side order.

### 3.4 Stock consideration — **VERIFIED**

- LEGACY/RULEBOOK input stock = `Products.TotalStock`, read from whichever
  copy the query targets:
  - `local` mode → central OrderNMC copy of `Products` (post pre-order sync).
  - `remote` mode → the branch DB directly, no `StoreName` column needed
    (single-store connection).
  - warehouse mode → central copy, `StoreName`-scoped
    (`sql/order_warehouse.sql`).
  - agent-synced store (e.g. NMV) → forced to `local` mode against the
    already-synced central copy (`order_process.py:661-669`).
- **Warehouse stock bridge** (what memory calls "NMW stock bridge" /
  "SMS SHP warehouse stock refresh bug"): before generating a *retail* store's
  order, `run_order_process` calls `refresh_warehouse_stock(store,
  warehouse_stock_source)` (`order_process.py:675-681`), which pulls the
  warehouse's own branch stock (or, for an AGENT-connection-type warehouse,
  its already-synced central copy) into this store's `SupplierStock` rows so
  the "Order Based Supplier Stock" / Website / supplier-compare views see it.
  **The previously-reported hardcoded-"NMW" bug is FIXED in the current
  working tree**: `_warehouse_stock_source_for(store)` resolves per-tenant via
  `LEGACY_WAREHOUSE_STOCK_SOURCE_BY_TENANT` env var
  (`order_process.py:51-67`), falling back to `LEGACY_WAREHOUSE_STOCK_SOURCE`
  (default `"NMW"`) only when no tenant-specific override exists. This is
  **uncommitted** (confirmed via `git diff`) but present in the working file —
  see §6.

### 3.5 Sales consideration — **VERIFIED**

- LEGACY engine: `ProductSaleInformation`, 90-day fixed window
  (`@ODATA`), filtered to `SeriesTransID=1` (retail) or also `SeriesName='TO'`
  for warehouse. "Recency" gate (`recencydays`, store-configurable, default
  15 retail / 90 warehouse — `service.DEFAULT_RECENCY_DAYS`,
  `service.WAREHOUSE_RECENCY_DAYS`) requires a sale within N days *and* that
  the last sale is not older than the last GRN (`lastsaledate >=
  LastReceivedDate`), i.e. "has this still been actively selling since it was
  last restocked."
- RULEBOOK engine: same table, same 90-day window
  (`params['window_days']`), computed per-product in
  `sql/order_rulebook_inputs.sql` (bill/line frequency, max-bill-qty, max-day-
  qty, last-sale, last-received), evaluated against the recency/receipt rules
  in Python.
- `abnormal_sales_service` (owned by `modules.procurement`, called from
  `legacy_order.router`) can retroactively exclude a bill's quantity from this
  window via `DontConsiderInOrder` (see §3.6) — **this writes to OrderNMC
  directly**, a clear coupling point for consolidation.

### 3.6 Scheme and discount treatment — **PARTIAL**

- No scheme/discount term appears in the quantity formula of either engine
  (confirmed by full read of `order_local.sql`/`order_warehouse.sql`/
  `quantity_profile_t.py` — neither references `Discount`, `Scheme`, `Free`,
  or `Offer` fields in the qty math).
- **IsOffer** flag (`order_process.py:330-350`, `repository.
  backfill_is_offer`, `repository.py:1917-1949`): a *display* flag, not a
  quantity input — set once per product per order-generation run (and
  refreshed on every grid read) when `PurchaseTrans.FreeQty > 0` exists for
  that product (excluding internal-transfer `InvoiceSeries='TI'` rows). Shown
  in the Qty Check/Pending/By-Supplier grids as a 🎁 icon so the operator
  knows a free-qty offer previously applied; does not change `OrderQty`.
- `LastOfferBaseQty`/`LastOfferFreeQty` (`_LAST_OFFER_PATTERN_APPLY`,
  `repository.py:1144+`) surfaces the most recent offer's base/free split for
  display, likewise read-only/informational.
- Export remarks (`order_export._apply_export_remarks`) let the operator
  attach a short free-text note (e.g. "9+1") per exported line — **manual
  annotation, not a calculated discount**.
- `_MASTER_STOCK_SQL`/`_MASTER_STOCK_SQL_CENTRAL` (branch/central stock pull
  for the Supplier Stock Distribution feature) compute `ProductDiscPercent`
  from `PurchaseTrans.PurchasePrice`/`ItemCost` — used only for display in the
  supplier-stock comparison, not for reorder qty.
- **No MOQ/min-order-value logic found anywhere in `legacy_order/*`** —
  confirmed by `Grep` for `min.*order.*value|minimum.*order|MOQ` across the
  whole module tree (no matches). **VERIFIED absence**, not merely unobserved.

### 3.7 Supplier stock consideration — **VERIFIED**

Yes, legacy order reads supplier stock, but only for **supplier selection/
export UI, never for the reorder-quantity formula itself**:
- `repository.orders_by_supplier(mode='stock')` joins `SupplierStock` via
  `SupplierProductMatch` to show live supplier stock/rack alongside the open
  order lines (`repository.py:1209-1346`).
- `repository.supplier_stock_compare` builds a per-product "every supplier's
  live stock/offer/discount" card (`repository.py:1347-1401`) — the "Supplier
  Web panel compare" feature from memory.
- `repository.remove_unavailable_from_supplier` bulk-drops assigned lines
  whose supplier stock is `<=0` or unmatched (`router.py:644-660`).
- `refresh_warehouse_stock` (§3.4) populates `SupplierStock` for the internal
  warehouse-as-supplier case.
- `quantity_profile_t.evaluate_profile_t`'s `confirmed_pending` input
  (intended to subtract already-placed-but-unreceived supplier orders from
  `net`) is **always 0** in the current wiring — `rulebook_order.
  evaluate_rows` hardcodes `"confirmed_pending": 0` (`rulebook_order.py:231`),
  and the module's own docstring states *"Confirmed supplier pending is 0
  until PRR-STK-PENDING names its source"* (`quantity_profile_t.py:7-8`).
  **UNKNOWN/owner-decision item**: this rule (PRR-STK-PENDING) is defined in
  the Rules Registry naming scheme but has no data source wired in yet —
  flagged for the Procurement-side investigation to confirm whether a source
  now exists on their side.

### 3.8 Minimum order quantity / minimum order value rules — **VERIFIED absent**

No MOQ or minimum-order-value gating exists in Legacy Order (see §3.6). The
closest analogues are the **demand-floor formulas** (`minqty`/`min_qty`) which
set a floor on *when a product is ordered at all*, not a floor on total order
value or total units per supplier. If the owner wants MOQ/min-order-value
enforcement in the consolidated engine, it does not currently exist on either
side of Legacy Order and would need to be designed new (or may already exist
in the Procurement Workspace — **defer to the other investigation**).

### 3.9 Pack size and unit conversion — **VERIFIED**

`Products.SaleUnit` is the pack size for every quantity conversion:
`OrderQty = CEILING((maxqty - TotalStock) / SaleUnit)` (LEGACY) and
`packs = CEILING(net / sale_unit)` (RULEBOOK). A missing/zero `SaleUnit`
blocks the RULEBOOK line entirely (`BLOCKED_SALE_UNIT`,
`quantity_profile_t.py:71-73`); LEGACY's SQL instead falls through to
`CASE ... ELSE 0 END` (silently orders 0 rather than raising a warning) when
`SaleUnit` is not `>0` (`order_local.sql` final SELECT's `Orderqty` CASE).
This is an **asymmetry between the two engines**: RULEBOOK surfaces the
missing-pack-size condition as an explicit reason code; LEGACY just produces
qty 0 with no distinguishing flag. Worth flagging for consolidation design.

### 3.10 Exclusions and manual overrides — **VERIFIED**

- **Skip rules** (`repository.py:2035-2149`, schema `sql/0010_order_skip_
  rules.sql`): `SKIP_MODES = {"current_refresh": "Current Order",
  "until_next_sales": "Until Next Sales", "until_next_demand": "Until Next
  Demand"}`. Matches memory note "3 skip modes" exactly.
  `PERSISTENT_SKIP_MODES = ("until_next_sales", "until_next_demand")` carry
  across order regenerations via `dbo.OrderProductSkip` until the product
  sells again (cleared by `apply_carried_skips`, called inside
  `insert_data_into_destination` for both engines, `order_process.py:351-354`).
- **Manual Qty edit**: `repository.update_order_qty` /
  `repository.update_qty_check` — direct `OrderQty` overwrite, remark
  auto-generated (`"OrderQty Changed N Add/Less"`, `"Don't Want to Order"`).
- **"Don't Consider In Order"** (abnormal-sale bill-level exclusion, shared
  with Procurement) feeds `ProductSaleInformation.DontConsiderInOrder`, read
  by both engines' sales-window queries (§3.5/§3.6).
- **Reset Pending** (`repository.reset_pending_qty_check`): bulk-reverts
  unassigned lines' `OrderQty` back to the generated `OrgOrderQty`, discarding
  unsaved manual edits.
- **Restore by OrderId** (`repository.restore_backup_order`,
  admin-only, `repository.py:2617+`): explicit recovery of a specific backup
  order's rows onto the current order, distinct from the Compare heuristics.

### 3.11 Order comparison functionality — **VERIFIED**

`repository.compare_previous_order` (`repository.py:2519-2574`) ports
`Form1.CompareOrderManagement` as 4 atomic SQL rules against
`OrderManagementBackup`:
1. Backup line fully assigned (status=1, has supplier+qty) → carry
   supplier+qty forward, mark current status=2 (processed).
2. Backup line still open but had a supplier+qty chosen → mark current
   status=2, don't copy supplier/qty.
3. Backup line manually zeroed by the operator (qtycheck=1, OrderQty=0,
   had a remark) → mark current status=2, no recalculation.
4. Stock sold since the backup → reduce `OrderQty` by what was already
   ordered (`OrgOrderQty - omb.OrQty`), reopen as status=0, tag
   `WantedType='After Order Sold'`.

Three compare "modes" exist (`rulebook_order.COMPARE_MODES`):
`PREVIOUS_PENDING` (compare against the single previous order — original VB
behaviour), `TODAY` (compare against every earlier order generated *today*,
oldest-first, newest decision wins — `service._compare_todays_previous`),
`NONE`, `HO` (warehouse order, never compared). Per-store setting persisted in
`dbo.LegacyOrderEngine.CompareMode` (`rulebook_order.py:148-187`). There's also
a **separate dry-run compare** — `rulebook_order.compare_engines` /
`compare_workbook` — that computes both LEGACY and RULEBOOK orders from the
same data **without writing anything** and emits an Excel workbook
(`GET /engine/{store}/compare.xlsx`, admin-only). This is the "Legacy vs
NEXORA order comparison" validation harness referenced in memory — confirmed
it lives **inside** `legacy_order/rulebook_order.py`, not in a separate
`procurement/legacy_order_parity.py` module as the memory hint speculated.
**No such separate parity module exists** — confirmed by `Grep`/file search;
the harness is the one described here.

### 3.12 Order scheduling — **VERIFIED**

`evening_order.py`: a scheduled "second order" run for a configurable list of
stores, default `18:25`, settings in `dbo.LegacyOrderSchedule`
(`evening_order.py:37-53`), one store at a time, each followed by a
same-day-previous-order compare. Claimed per-day via a conditional
`LastRunDate` UPDATE so two backends on the same OrderNMC can't double-run
(docstring, `evening_order.py:9-10`). Catch-up window
(`LEGACY_EVENING_ORDER_CATCHUP_MINUTES`, default 180 min) lets a backend that
was down at the scheduled time still run. Separately, `auto_sync.py` runs a
background sync-only loop (not order generation).

### 3.13 Export and final output generation — **VERIFIED**

See `order_export.py` in full (945 lines, read in full above). Key facts:
- Formats: `.xlsx` (openpyxl), `.xls` (xlwt, BIFF binary — explicit owner
  request to match a downstream consumer expecting old binary format), `.csv`
  (UTF-8 BOM), and PNG images (dark-themed, 20 rows/image, for WhatsApp
  sharing) — `order_export.py:224-481`.
- Two export flows: **By Supplier** (`export_order`, assigns status 0→1 for
  the rows still in the grid, then exports) and **Pending** (`export_pending_
  order`, read-only, no assignment).
- Legacy fixed column layout: `S.No., ProductName, OrderQty, SaleUnit, MRP,
  ProductCode, Discount, Category, SubLocation[, Rack]` (`_layout_fixed`,
  `order_export.py:589-607`) — `Category` is *predicted* from
  SubLocation/ProductName/UnitDescription text heuristics
  (`_predict_category`, `order_export.py:64-83`), not a stored field.
- Configurable column export (`columns` request param) lets the operator pick
  a subset; `product_code/product_name/order_qty` are always force-included
  server-side regardless of client selection (`_EXPORT_REQUIRED_COLUMNS`,
  enforced as a security/contract invariant, not just UI convenience).
- Deliberately NOT ported: `UpdateSupplierStockAfterExport` (the legacy VB
  stock-decrement-on-export step) — explicit product decision documented in
  the file header (`order_export.py:8-13`) to avoid double-counting against
  the independent sync-driven Supplier Live Stock pipeline. **Important for
  consolidation**: if the new unified engine reintroduces any stock
  decrement on export, it must not collide with that sync pipeline.

### 3.14 Tenant and store-level filtering/isolation — **VERIFIED**

- Every repository query is explicitly `WHERE StoreName = ?` /
  `WHERE storename = ?` scoped — no cross-store leakage found in any function
  read.
- Tenant resolution: `router._scope_tenant` (`router.py:172-202`) resolves the
  path's `store_name` to its platform tenant via
  `database.platform_tenant_id_by_store_name`, then calls
  `database.set_active_tenant(tenant_id)` for the duration of the request —
  this picks which physical OrderNMC/OrderSMS/OrderSuccess database the
  connection pool targets (multi-tenant HO support, memory note "OrderNMC
  per-tenant split"). Must be an **async** generator dependency — the
  docstring (`router.py:182-192`) documents a real bug that was hit and fixed:
  a sync generator dependency's enter/exit halves could land in different
  `contextvars` Contexts under FastAPI's threadpool, corrupting
  `reset_active_tenant`.
- Non-admin store-user scoping (`router.py:41-169`): three regex path-sets
  (`_VIEWER_READ_PATHS`, `_STORE_WRITE_PATHS`, `_PM_WRITE_PATHS`) plus
  `_user_owns_store`/`_user_store_codes` (reads `dbo.user_store_roles` from the
  **platform** DB, not OrderNMC) gate exactly which store a non-admin caller
  may touch. `/stores` is special-cased (`_NO_PARAM_READ_PATHS`) because it
  has no `{store_name}` path param — `list_stores` itself filters the response
  to the caller's own store(s) (`router.py:239-265`).

### 3.15 User permission enforcement — **VERIFIED**

Three permission tiers, all FastAPI `Depends`:
1. `require_admin` (`router.py:35-38`) — `has_unrestricted_scope(current_
   user)` (platform admin only). Gates DB recovery, engine/compare-mode
   settings, evening-order schedule, restore-by-OrderId.
2. `require_order_console_access` (`router.py:139-160`, the **router-level
   default dependency** applied to the whole router via
   `dependencies=[Depends(require_order_console_access), Depends(_scope_
   tenant)]`, `router.py:204-207`) — admin, or a non-admin store user
   restricted to their own store's read/write paths as enumerated in
   `_VIEWER_READ_PATHS`/`_STORE_WRITE_PATHS`.
3. `require_admin_or_store_pm` (`router.py:163-169`) — admin, or a
   purchase-manager-role login (`_is_purchase_manager`, checks `role_names`
   for a case-insensitive `"purchase"` substring) assigned to that store.
   Gates workflow finalize/reopen, PM order-entry, supplier portal/harvest/
   match-review-confirm (`_PM_WRITE_PATHS`).

Every individual route then *also* carries its own `Depends(...)` (e.g.
`require_admin` on `/db/recover`), so the router-level default is a floor, not
a ceiling — a route can tighten but the comments confirm (`router.py:46-47`,
`92-98`) this is deliberate defense-in-depth, not redundancy to remove
casually.

---

## 4. Where Legacy Order touches the Procurement module (for the other
investigation's reference — not expanded here)

| Legacy Order file:line | Procurement symbol called | Nature of coupling |
|---|---|---|
| `router.py:15-16` | `modules.procurement.abnormal_sales_service`, `modules.procurement.pm_schemas.DontConsiderUpdate` | Abnormal-sale review UI lives in Order Workspace but is computed/written by the Procurement module |
| `router.py:1113-1126` | `abnormal_sales_service.legacy_abnormal_sales`, `.set_dont_consider` | Same as above — HTTP routes |
| `order_process.py:35` | `modules.procurement.product_identity.collapse_generated_payload` | Dedup of generated order rows (new, untracked import) |
| `repository.py:9` | `modules.procurement.product_identity.collapse_lines` | Dedup of several grid-read functions (new, untracked import) |
| `rulebook_order.py:36` | `modules.procurement.quantity_profile_t.evaluate_profile_t` | The entire RULEBOOK engine's quantity math |
| `rulebook_order.py:198` | `modules.procurement.rules_resolution.REGISTRY` | RULEBOOK's effective parameters (PRR-QTY-* rule IDs) |
| `repository.py:968` (`sync_supplier_product_match_from_mapping`) | `modules.product_mapping.repository.supplier_bridge_targets` | Cross-store product identity bridge (NMW stock → other stores' SupplierProductMatch) — `product_mapping` is a separate module, not `procurement`, noted for completeness |

This confirms Legacy Order is **not** a fully isolated module today — it
already depends on three Procurement-owned Python modules
(`abnormal_sales_service`, `product_identity`, `quantity_profile_t`,
`rules_resolution`). Any consolidation plan that "removes" the Procurement
Workspace module wholesale must either keep these four files (and their own
transitive deps) alive, or port their logic into `legacy_order` directly.

---

## 5. Conflicts / open owner decisions flagged during this investigation

1. **"Unified procurement workspace directive" vs. "Keep legacy Order
   Workspace unchanged"** (memory notes) — the code shows the *current* state
   is "Legacy Order Workspace is frozen UI-wise, but gained a RULEBOOK engine
   option underneath it that reuses Procurement's quantity formula." This is
   consistent with a "consolidate around Legacy Order" direction (the user's
   stated goal for this investigation) but is **not** the literal "merge OW +
   Procurement into one workspace" directive from the older memory note. No
   code contradicts the newer direction; flagging only because the two
   historical directives are not the same thing. **UNKNOWN/owner-decision**:
   confirm which directive is authoritative going forward (this investigation
   assumes the user's current framing in the task prompt is authoritative).
2. **PRR-STK-PENDING unresolved** (§3.7) — the RULEBOOK engine's `net` formula
   has a live placeholder (`confirmed_pending=0`) for subtracting
   already-placed supplier orders. Needs an owner/Procurement-side decision
   on the data source before RULEBOOK can be considered feature-complete
   relative to what a real purchase manager would expect.
3. **LEGACY vs RULEBOOK missing-pack-size asymmetry** (§3.9) — LEGACY SQL
   silently orders 0 when `SaleUnit` is missing/zero; RULEBOOK surfaces
   `BLOCKED_SALE_UNIT` as an explicit reason. If LEGACY is to be retired in
   favour of RULEBOOK-under-Legacy-Order's-tables, this behavioural diff will
   change what appears on screen for products with a bad `SaleUnit`.

---

## 6. Uncommitted working-tree changes relevant to this investigation (read via `git diff`, NOT modified by this investigation)

- `backend/modules/legacy_order/order_process.py`: adds
  `_sync_agent_source_stock` (forces a live device sync of
  Products/PurchaseTrans/Batches for an AGENT-connection-type warehouse
  source before `refresh_warehouse_stock` reads it), with a
  `LEGACY_WAREHOUSE_STOCK_SYNC_MIN_INTERVAL_SECONDS` (default 900s) floor to
  avoid redundant syncs when several retail stores order close together
  against the same warehouse. Also adds `collapse_generated_payload` call in
  `insert_data_into_destination` to dedupe same-product-code generated rows
  (demand line vs. zero "Additional Row" copy) — quantity is never summed,
  the "better" row wins (`product_identity._prefer_generated`).
- `backend/modules/legacy_order/repository.py`: adds `collapse_lines` to
  `orders_by_supplier`, `all_open_orderables`, `assigned_orders`,
  `all_assigned_orders`, `qty_check_rows`, `pending_order_rows` — dedupes rows
  that fan out from a 1-product-to-many-SupplierProductMatch/SupplierStock
  join, keeping one row per (store, product[, supplier]) identity. Also
  changes `assigned_orders`'s join from `LEFT JOIN SupplierProductMatch/
  SupplierStock` to `OUTER APPLY ... ORDER BY ISNULL(Stock,0) DESC TOP 1` so
  the richest-stock mapping wins instead of silently duplicating the order
  line.
- Both changes are **confirmed exercised** by the new untracked test file
  `backend/tests/test_legacy_order_warehouse_stock_sync.py` (read in full —
  6 tests, all mocking the seam cleanly; explicitly tests that the sync is
  "not hardcoded to one store name", directly answering the memory note's
  concern). **VERIFIED present and consistent with its own tests**; this
  investigation did not execute the tests (read-only mandate).

---

## Evidence index (file:line quick reference)

| Topic | Primary file:line |
|---|---|
| Router permission gates | `router.py:35-169, 204-207` |
| Tenant scoping dependency | `router.py:172-202` |
| Order-process orchestration | `service.py:365-530` |
| LEGACY core SQL (retail) | `sql/order_local.sql:1` |
| LEGACY core SQL (remote) | `sql/order_remote.sql:1` |
| LEGACY core SQL (warehouse) | `sql/order_warehouse.sql:1-157` |
| LEGACY write path | `order_process.py:205-363` |
| Warehouse stock source resolution | `order_process.py:41-67, 675-681` |
| Agent-source live-sync fix (uncommitted) | `order_process.py:467-589` (diff) |
| RULEBOOK engine | `rulebook_order.py:1-465` |
| RULEBOOK quantity formula | `quantity_profile_t.py:50-118` |
| RULEBOOK inputs SQL | `sql/order_rulebook_inputs.sql:1-58` |
| Dedup helper (shared w/ Procurement) | `product_identity.py:1-108` |
| Supplier best-margin auto-assign | `repository.py:1666-1845` |
| Skip rules | `repository.py:2035-2149`, `sql/0010_order_skip_rules.sql` |
| Compare previous order (4 rules) | `repository.py:2519-2574` |
| Compare modes / dry-run harness | `rulebook_order.py:148-187, 317-465` |
| Evening order scheduler | `evening_order.py:1-90+` |
| Export builder | `order_export.py:1-945` |
| Abnormal-sales boundary w/ Procurement | `abnormal_sales_service.py:1-146`, `router.py:1113-1126` |
