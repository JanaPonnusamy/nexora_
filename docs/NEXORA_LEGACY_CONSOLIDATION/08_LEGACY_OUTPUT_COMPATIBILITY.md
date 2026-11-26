# Legacy Order — Calculation Table & Output Compatibility

Companion to `02_LEGACY_ORDER_DEPENDENCY_MAP.md`. Read-only investigation;
no files modified, no DB queried (all findings from source + SQL files on
disk). Confidence tags: **Verified** (read the exact code/SQL),
**Partial** (read code, did not execute/trace DB contents),
**Inferred** (reasoned, not directly confirmed), **Unknown**.

---

## 1. Calculation table

| Calculation name | Source (file:line) | Input data (tables/fields) | Calculation (formula) | Output field | Consumers | Tenant scope | Confidence |
|---|---|---|---|---|---|---|---|
| **LEGACY — AvgSalesQty** | `sql/order_local.sql:1` (CTE `ProductSaleInfo`) | `ProductSaleInformation.Quantity` (90-day sum), `COUNT(DISTINCT ID)` as Frequence | `CEILING(slsqty / Frequence)` | `AvgSalesQty` (internal, feeds minqty/WantedType) | LEGACY minqty, WantedType text | Store (`@storename`) | Verified |
| **LEGACY — MinQty (demand floor)** | `sql/order_local.sql:1` | `slsqty` (90-day sum), `@minday` (13 retail / 32 warehouse), `AvgSalesQty` | `MAX( CEIL((slsqty/90.0)*@minday), AvgSalesQty )` | `minqty` → `OrderManagement.MinQty` | Eligibility gate (`minqty > TotalStock`), MaxQty comparison | Store | Verified |
| **LEGACY — MaxQty (target cover)** | `sql/order_local.sql:1` | `slsqty`, `@maxday` (18 retail / 35 warehouse), `MaxSalesQtyInBill` (single biggest bill line in 90d) | `MAX( CEIL((slsqty/90.0)*@maxday), MaxSalesQtyInBill )` | `maxqty` → `OrderManagement.MaxQty` | OrderQty formula | Store | Verified |
| **LEGACY — OrderQty** | `sql/order_local.sql:1` (final SELECT) | `maxqty`, `TotalStock`, `SaleUnit` | `TotalStock=0 AND (maxqty-TotalStock)<=0 → 1`; `elif SaleUnit>0 → CEIL((maxqty-TotalStock)/SaleUnit)`; `else → 0` | `Orderqty` → `OrderManagement.OrderQty` + `OrgOrderQty` (dup) | Qty Check grid, Pending grid, Export | Store | Verified |
| **LEGACY — Eligibility gate** | `sql/order_local.sql:1` (final SELECT `WHERE`) | `maxqty, TotalStock, SaleUnit, minqty, lastsaledate, LastReceivedDate, @recencydays` | `(maxqty-TotalStock)/SaleUnit > 0 AND minqty>TotalStock AND lastsaledate>=LastReceivedDate AND lastsaledate>=today-recencydays` | row included/excluded | — | Store | Verified |
| **LEGACY — Additional Row (rare mover)** | `sql/order_local.sql:1` (2nd `UNION ALL` branch) | `TotalStock, minqty, Frequence, slsqty, lastsaledate, LastReceivedDate` | `TotalStock<=1 AND minqty<=1 AND Frequence>1 AND slsqty>1 AND lastsaledate>=today-recencydays AND lastsaledate>LastReceivedDate AND NOT already in main branch` | `OrderQty=1, WantedType='Additional Row'` — **zeroed to 0, Status=2 by `insert_data_into_destination`** | Audit trail only; never actually ordered | Store | Verified |
| **LEGACY — Warehouse demand basis** | `sql/order_warehouse.sql:24-37` | `ProductSaleInformation.SeriesTransID=1 OR SeriesName='TO'` | Same AvgSalesQty/MinQty/MaxQty/OrderQty formulas as retail, but demand sum includes Transfer-Out to branches, not just retail billing | same fields | Warehouse (e.g. NMW) order only | Store (warehouse) | Verified |
| **RULEBOOK — gross (target cover)** | `quantity_profile_t.py:90-100` | `window_qty` (90d sum, configurable), `max_days`, `max_bill_qty`, `max_day_qty`, `bill_frequency` | `MAX(avg_daily*max_days, max_bill_qty, max_day_qty, avg_bill)`, first-listed term wins ties | `gross` (internal) | `net` calc | Store | Verified |
| **RULEBOOK — net** | `quantity_profile_t.py:101` | `gross`, `total_stock`, `confirmed_pending` (always 0 today, see §3.7 of dependency map) | `gross - total_stock - confirmed_pending` | `net` (internal) | packs calc | Store | Verified |
| **RULEBOOK — packs (OrderQty)** | `quantity_profile_t.py:115-118` | `net`, `sale_unit` | `CEILING(net / sale_unit)`; `net<=0` → 0 (or 1 if rare-mover) | `packs` → `OrderManagement.OrderQty` | Same downstream as LEGACY (shared tables) | Store | Verified |
| **RULEBOOK — MinQty (legacy-parity floor)** | `rulebook_order.py:254-255` | `window_qty`, `params['min_days']`, `line_frequency` | `MAX(CEIL(avg_daily*min_days), CEIL(window_qty/line_frequency))` | `MinQty` → `OrderManagement.MinQty` (parity field only, not used in packs calc) | Display/compare only | Store | Verified |
| **RULEBOOK — Eligibility/exclusion reasons** | `quantity_profile_t.py:71-88` | `sale_unit`, `dont_consider`, `window_sales_qty`, `last_sale`, `recency_days`, `last_received` | Ordered checks: `BLOCKED_SALE_UNIT → EXCLUDED_DONT_CONSIDER → EXCLUDED_NO_SALES → REVIEW_RECENCY → SUPPRESSED_NO_SALE_SINCE_RECEIPT` | `reason` code | compare_engines summary, dry-run workbook | Store | Verified |
| **RULEBOOK — Rare mover** | `quantity_profile_t.py:35-47, 104-112` | `stock, min_qty, line_frequency, window_qty, last_sale, last_received` | `stock<=1 AND min_qty<=1 AND line_frequency>1 AND window_qty>1 AND last_sale>last_received` → 1 pack, `RARE_MOVING_MANUAL_REVIEW` | `packs=1`, `WantedType='Rule Book · Rare Moving — Manual Review'` | Qty Check grid (manual review) | Store | Verified |
| **Auto-Assign margin** | `repository.py:1686-1697` | `PurchaseTrans.MRP, ItemCost, StockReceived, FreeQty` (last 5 IV receipts) | `net_cost = ItemCost*received/(received+free)`; `margin% = (MRP-net_cost)/MRP*100` | `margin` per supply | `pick_auto_assign_supplier` | Store | Verified |
| **Auto-Assign supplier pick** | `repository.py:1700-1725` | per-supplier margin/count/latest-date across last-5 receipts; fallback: purchase-receipt frequency, then `OrderManagementBackup` assignment frequency | `max by (round(margin,2), count, latest_date)`; else most-frequent active supplier | `OrSupplierCode`/`OrSupplier` (on assign apply) | By Supplier / Export | Store | Verified |
| **IsOffer flag** | `order_process.py:330-350`, `repository.py:1917-1949` | `PurchaseTrans.InvoiceSeries<>'TI' AND FreeQty>0` (EXISTS) | boolean set-based UPDATE, once per order-gen run + refreshed on every grid read | `OrderManagement.IsOffer` | Qty Check/Pending/By-Supplier grid 🎁 icon | Store | Verified |
| **Compare-previous-order (4 rules)** | `repository.py:2519-2574` | `OrderManagement` × `OrderManagementBackup` (joined on ProductCode+StoreName) | 4 mutually exclusive UPDATE rules (carry-forward / mark-processed / respect manual zero / "After Order Sold" reopen with reduced qty) — see dependency map §3.11 | `Status, OrQty, OrSupplier, OrderQty, WantedType, Remarks` | Compare dialog, Qty Check (status filtering) | Store | Verified |
| **Category prediction (export only)** | `order_export.py:51-83` | `SubLocation`, `ProductName`, `UnitDescription` text heuristics | keyword match (TAB/SYP/VET/INH/RC/RESP/PASTE, then name-based fallback) → `TAB/SYP/PASTE/VET/INH/RC/RESP/OTHER` | `Category` (export-only column, never stored) | Excel export `_layout_fixed` | Store | Verified |

---

## 2. Field-level output mapping (final Order Workspace grid / export)

Grid sources: `qty_check_rows`/`pending_order_rows`
(`repository.py:1848-1915`), `orders_by_supplier`/`assigned_orders`
(`repository.py:1209-1491`). Export sources: `order_export._layout_fixed`
(legacy fixed layout) and `_EXPORT_COLUMN_MAP` (configurable layout).

| Visible/exported field | Source (file:line + table.column) | NEXORA/Procurement equivalent | Risk of changing |
|---|---|---|---|
| ProductCode | `OrderManagement.ProductCode` (written from LEGACY SQL `productcode` / RULEBOOK `d["ProductCode"]`, `order_process.py:119-146`) | Likely `sync.Products`/VPL product_code on Procurement side — **see other investigation** | **High** — primary join key for every downstream screen/export/WhatsApp/supplier-match; `product_identity.canonical_product_code` already exists specifically to paper over float/str mismatches on this field |
| ProductName | `OrderManagement.ProductName` | Procurement VPL product name — see other investigation | Low — display only |
| OrderQty | `OrderManagement.OrderQty` (LEGACY `Orderqty` CASE / RULEBOOK `packs`) | Procurement's `final_qty`/`suggested_qty` equivalent — see other investigation | **High** — the actual reorder decision; any formula change changes real purchasing |
| OrgOrderQty | `OrderManagement.OrgOrderQty` (duplicate of OrderQty at generation time, `COLUMN_MAP` maps `OrderQty` twice, `order_process.py:141-142`) | None known on Procurement side | Medium — used by `reset_pending_qty_check` and compare-rule 4 as the "original" baseline; removing it breaks both |
| TotalStock | `OrderManagement.TotalStock` ← `Products.TotalStock` at generation time (a snapshot, not live) | Procurement stock source — **see other investigation (Cycle/Refresh)** for whether it reads the same `Products.TotalStock` or a different live-stock query | Medium — stale by design (snapshotted at order-gen time); Qty Check screen does not re-read live stock |
| SaleUnit | `OrderManagement.SaleUnit` ← `Products.SaleUnit` | Pack-size field, presumably shared `Products` table — see other investigation | **High** — both engines divide by this; zero/null causes silent 0-qty (LEGACY) or explicit block (RULEBOOK) |
| MRP | `OrderManagement.MRP` ← `Products.MRP` | Shared `Products.MRP` — see other investigation | Low — display + margin calc input (auto-assign) |
| SLSQty | `OrderManagement.SLSQty` (90-day sales sum) | Procurement's window-sales equivalent — see other investigation | Medium — informational on grid, not re-derived from a live query after generation |
| UnitDescription | `OrderManagement.UnitDescription` ← `Products.UnitDescription` | shared `Products` — see other investigation | Low |
| SubLocation | `OrderManagement.SubLocation` ← `Products.SubLocation` | shared `Products` — see other investigation | Low–Medium (feeds export `Category` prediction and Rack sort) |
| WantedType | computed per-engine (`sql/order_local.sql` CASE chain / `rulebook_order.WANTED` dict) | No direct Procurement equivalent known; RULEBOOK's `determinant`→label mapping is Legacy-Order-specific | Medium — purely explanatory text shown on grid, but operators read it to judge *why* a qty was suggested; changing label text/logic affects operator trust, not the number itself |
| ProductTypeName | `OrderManagement.ProductTypeName` (`'Pharma'/'Non Pharma'` from `Products.ProductType`) | shared `Products.ProductType` — see other investigation | Low — used as a filter only |
| Status | `OrderManagement.Status` (0=open, 1=assigned, 2=processed/compared) | No direct equivalent — this is Legacy Order's own workflow state machine | **High** — every grid query (Qty Check, Pending, By-Supplier, Assigned) filters on this; it IS the Legacy Order workflow |
| Qtycheck | `OrderManagement.Qtycheck` (0=unreviewed, 1=reviewed) | No direct equivalent | **High** — second half of the workflow state machine; NULL=0 pitfall already caused a real bug (`order_process.py:214-220` comment) |
| IsOffer | `OrderManagement.IsOffer` (see calc table) | No direct equivalent | Low — display icon only |
| SkipReason / SkippedAt / SkippedBy | `OrderManagement` + `dbo.OrderProductSkip` (sql/0010) | No direct equivalent — Legacy-Order-specific skip-mode system | Medium — the persistent skip modes (`until_next_sales`/`until_next_demand`) carry state across order regenerations; losing this silently re-surfaces intentionally-skipped lines |
| Remarks | `OrderManagement.Remarks` (auto-generated diff text, compare-rule text, skip text, or operator-typed) | No direct equivalent | Low — audit/explanatory text |
| OrSupplier / OrSupplierCode | `OrderManagement.OrSupplier(Code)` (set on assign) | Procurement's supplier-assignment field — see other investigation | **High** — drives Export's supplier grouping and WhatsApp auto-send targeting |
| SupplierProductCode / SupplierProductName | `SupplierProductMatch`/`SupplierStock` via join (recently changed to `OUTER APPLY TOP 1 ... ORDER BY Stock DESC`, see dependency map §6) | Procurement's supplier-product-match — see other investigation | Medium — export-only enrichment columns; the uncommitted fix changed how duplicates are resolved (richest-stock wins) |
| Rack | `SupplierStock.Rack` (via match join, mode='stock' only) | Procurement equivalent — see other investigation | Low — export sort key only in stock mode |
| Discount (export) | `PurchaseTrans`-derived `ProductDiscPercent` (supplier-stock pull only, `repository.py:769-873`) — **NOT** the same as any OrderManagement column; only appears in Export's fixed layout when `has_rack` (stock mode) | Procurement discount field — see other investigation | Low — display only, not fed back into quantity |
| Category (export) | Predicted, not stored (`order_export.py:51-83`) | None — Legacy-Order-export-only convenience | Low — but changing the heuristic changes which supplier-facing category label appears on every exported sheet; some downstream human/manual process may depend on exact category strings |
| S.No. | Row position in the sorted export list (1-based) | N/A | Low |

**Export-only derived columns** (not on the live grid, computed at export
time, see `order_export._EXPORT_COLUMN_MAP`/`_PENDING_COLUMN_MAP`): Discount,
Category, Rack (stock mode), Remarks (export-remark, operator-typed per
export, never persisted to OrderNMC — `order_export.py:635-655`), Supplier
Code/Name (via the match join above).

**Export file naming/format** (risk: Low for the number itself, but these are
owner-specified formats consumed by downstream humans/scripts — changing them
silently could break an established workflow):
- By-Supplier: `"{supplier_name} {store_name}   {ddMMyyyy}[ {name_suffix}]"`
  (3 spaces between supplier and store, owner-specified — `order_export.py:
  901-902`).
- Pending: `"Pending {ddMMyyyy} {order_no or ddMMyyyy}"`.
- Split (`split_size`): produces a `.zip` of `"<base> Part n of m.<ext>"`
  files, matching the legacy VB "split size" behaviour the desktop client
  unpacks into the order folder.
- `.xls` requested specifically preserves the exact legacy VB header
  spellings including the typo `"Discound"` (`_VB_HEADER`, `order_export.py:
  687`) — **intentional**, because downstream supplier-side consumers were
  built against that exact VB output; "fixing" the typo would be a breaking
  change to an external process, not an improvement.

---

## 3. Explicit conflicts/gaps for the consolidation decision

1. **RULEBOOK's `confirmed_pending=0` placeholder** (calc table row 9) means
   RULEBOOK's `net` formula is currently *equivalent to* ignoring
   already-placed supplier orders — if Procurement's engine already resolves
   this (PRR-STK-PENDING), consolidating onto RULEBOOK-under-Legacy-Order
   should carry that resolution over; if not, both engines currently share
   the same gap. **Unknown** — needs Procurement-side confirmation.
2. **LEGACY vs RULEBOOK SaleUnit=0/NULL behaviour differs** (silent 0 vs.
   explicit `BLOCKED_SALE_UNIT`) — a consolidation onto one engine changes
   what the operator sees for these edge-case products.
3. **`OrgOrderQty`/`Status`/`Qtycheck`/Skip-state have no known Procurement
   equivalent** — these are Legacy-Order-specific workflow/state-machine
   columns that the whole Qty Check → Pending → Supplier-Assign → Export UI
   is built on top of. Any consolidation plan must either keep this state
   machine (recommended, since both engines already write through it) or
   design an equivalent before retiring `OrderManagement`'s current shape.
4. **Export's legacy `.xls` output intentionally preserves historical
   spelling/format quirks** for external consumers — flag before any
   "cleanup" of export code.

---

## Evidence index (file:line quick reference)

| Topic | Primary file:line |
|---|---|
| LEGACY calc SQL | `sql/order_local.sql:1`, `sql/order_warehouse.sql:1-157` |
| RULEBOOK calc | `quantity_profile_t.py:50-118`, `rulebook_order.py:241-312` |
| Auto-assign margin/pick | `repository.py:1686-1725` |
| IsOffer | `order_process.py:330-350`, `repository.py:1917-1949` |
| Compare-previous-order rules | `repository.py:2519-2574` |
| Qty Check / Pending grid field list | `repository.py:1848-1915` |
| By-Supplier / Assigned field list | `repository.py:1209-1346`, `1423-1493` |
| Export column maps | `order_export.py:589-632, 712-724` |
| Export filename rules | `order_export.py:896-926, 800-802` |
| OUTER APPLY stock-pick fix (uncommitted) | `repository.py` diff, `assigned_orders` |
