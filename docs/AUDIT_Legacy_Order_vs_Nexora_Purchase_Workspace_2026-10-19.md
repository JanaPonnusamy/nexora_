# Legacy Order Workspace vs Nexora Purchase Manager — Audit and Unified Design

**Status:** Decision-ready audit. **No production code was changed.**  
**Date:** 2026-10-19  
**Scope:** System A = Nexora Purchase Workspace (`frontend` Purchase Manager + `backend/modules/procurement`). System B = Legacy Order Workspace (`backend/modules/legacy_order` + web `OrderWorkspacePage` + desktop Stock Client `OrderWorkspace`).  
**Out of scope this pass:** VB.NET source at `D:\VBDOTNET\OrderManagement` (not in this repo). Legacy SQL in-repo is treated as the port of that engine. Live database timings were not measured.

**Confidence labels used below**

| Label | Meaning |
|---|---|
| Verified | Read from the cited source in this audit |
| Inferred | Behavior follows from the code, but a business name or POS column meaning is not defined in-repo |
| Undocumented | UI, comment, or older doc disagrees with the code that runs |
| Not measured | Required by the brief; no baseline captured in this session |

---

## 1. Executive summary

The two systems are **not two views of one order**. They are two procurement lifecycles that share a 90-day retail sales idea and a pack-ceiling quantity, then diverge on stock, recency, spike floors, what “wanted” means, and everything after the first quantity (review, supplier, export, receipt).

**Legacy** generates a store order by running `order_local.sql` / `order_remote.sql` / `order_warehouse.sql`, replacing `OrderManagement` for that store, then lets a buyer walk Qty Review → Pending → supplier assign → Excel export → workflow finalize. Order quantity is `CEILING((maxqty − TotalStock) / SaleUnit)`. `maxqty` is `MAX(CEILING((slsqty/90)*MaxDays), MaxSalesQtyInBill)` where `MaxSalesQtyInBill` is the largest **single sale line**. “Additional Row” lines are inserted and then **zeroed** (`Status = 2`). Default retail parameters in code: min 13, max 18, recency **15** days, window **hard-coded 90** days. Stock is `products.TotalStock`.

**Nexora** generates a refresh inside an active cycle: `decision_rules.evaluate` writes included products to the virtual product list, working items copy `suggested_qty` into `final_qty`, then the buyer reviews, assigns **one** supplier per line, exports, and reconciles GRN. Suggested packs are `CEILING(CEILING(GrossTarget − EffectiveAvailable) / SaleUnit)` with `GrossTarget = MAX(AvgDaily × MaxDays, max day sum, max bill sum, max sale line)`. Recency default is **10** days. Stock is latest-month `ProductTrans.StockInHand` (documented owner ruling; disagrees with `TotalStock` on a large share of a real catalogue). Pending purchase / in-transit / reserved are **always 0** in the loader. Rare-mover parity **keeps** a 1-pack line; legacy additional rows do not stay orderable.

**Do not start a unified UI build yet.** Four quantity conflicts change what gets ordered. They need an owner decision. The recommended target is: keep Nexora’s lifecycle (cycle, refresh, review, single-supplier assign, export, GRN) as the system of record, and feed it a **generation profile** that can reproduce legacy retail math when the business says the legacy result is the one that must match. Compact workspace layout and keyboard contract below are the UI target after those rules are locked.

**Go / no-go:** **NO-GO** for implementation. **GO** for the decision meeting in §18 and for a golden-test harness (Phase 0) that does not change order quantities.

---

## 2. Repository and dependency map

```
Store context
  Legacy: dbo.Stores (OrderNMC) → LAN branch DB or central copy or NMV agent
  Nexora: tenant + store_id → NEXORA_PLATFORM.sync.*

Generation
  Legacy: service.start_order_process
          → order_process.run_order_process
          → sql/order_local.sql | order_remote.sql | order_warehouse.sql
          → DELETE/INSERT OrderManagement (+ backup, Additional zero, IsOffer)
  Nexora: orchestration_service refresh
          → decision_repository.load_source
          → decision_rules.evaluate
          → VPL (INCLUDE only)
          → order_items_repository.generate_working_items

Buyer workspace
  Legacy web:  frontend/src/pages/legacy-order/OrderWorkspacePage.tsx
               frontend/src/services/legacyOrderService.ts
               API /api/legacy-order/*
  Legacy desktop: desktop/supplier-stock-client/src/App.jsx OrderWorkspace
                  desktop/supplier-stock-client/src/api/client.js
  Nexora: frontend/src/pages/procurement/PurchaseWorkspacePage.tsx
          frontend/src/components/procurement/ProductGrid.tsx
          frontend/src/components/procurement/purchaseValue.ts
          API /api/procurement/*

Downstream
  Legacy: order_export.py Excel; workflow finalize/reopen; remote_order_agent qty sync
  Nexora: assignment_service → export_service → reconciliation_rules / pending_service
```

| Concern | Legacy evidence | Nexora evidence |
|---|---|---|
| Authoritative generation | `backend/modules/legacy_order/sql/order_local.sql` (single statement) | `backend/modules/procurement/decision_rules.py` `evaluate` / `final_required` |
| Inputs | `order_process.py` binds `@ODATA`, `@minday`, `@maxday`, `@recencydays` | `decision_repository.load_source` |
| Buyer qty | `repository.update_qty_check`, `update_order_qty` | `workspace_repository.set_final_qty` |
| Docs that match code | None fully. SQL is the spec. | `docs/Nexora_Demand_Generation_Rules.md` matches `decision_rules.py` |
| Docs that lag code | — | `docs/Procurement_Decision_Flow.md`, `docs/Procurement_Business_Rules.md` PR-BR-004/007 (pre stock-netting / pre OR-gate). `docs/BUSINESS_RULES/PR-BR-001` and `PR-BR-002` are stubs. |

**Database writes during this audit:** none. **New tables / procedures:** none.

**Limitation:** `order_remote.sql` and `order_warehouse.sql` were not line-extracted in full. Retail local SQL was. Remote is the branch-scoped variant of the same engine (`order_process.py` selects it when `mode=remote`). Warehouse uses transfer-out demand and different default min/max/recency (`service.py` `WAREHOUSE_*`). Treat warehouse as legacy-only until that SQL is extracted the same way.

---

## 3. Legacy order-generation rule inventory

Rules below are **verified** from `order_local.sql` and the Python that runs it, unless marked otherwise.

### L-01 Window and sales eligibility

`@ODATA = today − 90 days` (`order_process.py` ~434). Sales CTE: `ProductSaleInformation` joined to `products`, `Transactiondate >= @ODATA`, `quantity > 0`, `SeriesTransID = 1`, `transactionvalidity = 0`, `p.isactive = 1`, `DontConsiderInOrder = 0`, store scoped. `slsqty = SUM(quantity)`. `Frequence = COUNT(DISTINCT ps.ID)`.

### L-02 Min and max cover (loose units)

```
minqty = MAX( CEILING((slsqty/90.0)*@minday), CEILING(slsqty/NULLIF(Frequence,0)) )
maxqty = MAX( CEILING((slsqty/90.0)*@maxday), MaxSalesQtyInBill )
```

`MaxSalesQtyInBill = MAX(Quantity)` on eligible sale **rows** (not day sum, not bill sum). The divisor **90.0 is hard-coded**, not `@ODATA`’s length. Defaults: `@minday=13`, `@maxday=18` (`service.py` `DEFAULT_MIN_DAYS` / `DEFAULT_MAX_DAYS`). Warehouse defaults 32/35.

### L-03 Main-line eligibility

All must hold:

- `lastsaledate >= today − @recencydays` (default **15**, env `LEGACY_RECENCY_DAYS`; warehouse **30**)
- `minqty > TotalStock`
- `(maxqty − TotalStock) / NULLIF(SaleUnit,0) > 0`
- `lastsaledate >= LastReceivedDate`

`lastsaledate` / `LastReceivedDate` come from `ProductTrans` (`MAX(LastBillDate)`, `MAX(LastgrnDate)`) **only where `LastBillDate` is inside the recency window**. Inferred: month-level ProductTrans cannot order “sale after GRN” inside a month. Nexora’s loader comment records that limitation (`decision_repository.py` ~122–129).

### L-04 Order quantity (packs)

```
CASE
  WHEN TotalStock = 0 AND (maxqty − TotalStock) <= 0 THEN 1
  WHEN SaleUnit > 0 THEN CEILING((maxqty − TotalStock) / SaleUnit)
  ELSE 0
END
```

Persisted as `OrderQty` and `OrgOrderQty`. Python does not recompute it.

### L-05 WantedType (label, not a quantity)

Outer label (overrides an earlier inner label): `Rare Moment` | `Min & Max Based MaxsaleQTY` | `Once Sold Last 90 days` | `Regular Order Based Min & Max` | union branch `Additional Row`. These strings classify why the row exists. They are not a second quantity.

### L-06 Additional Row

Union branch: `TotalStock <= 1 AND minqty <= 1 AND Frequence > 1 AND slsqty > 1` AND recency AND `lastsaledate > LastReceivedDate` (strict `>`, main branch uses `>=`) AND not already in the main gate. SQL sets `Orderqty = 1`. After insert, `order_process.py` ~227–231 sets `OrderQty = 0, OrgOrderQty = 0, Status = 2, Remarks = 'Additional'`. **The line is not an orderable quantity.**

### L-07 Product type

`producttype = 0` → Non Pharma, else Pharma.

### L-08 Stock

Order math uses `products.TotalStock`. No pending PO, in-transit, or reservation term in the SQL. Inferred: this is whatever the POS product master calls total stock, not a calculated available quantity.

### L-09 Regeneration

Per store: backup current `OrderManagement` into `OrderManagementBackup` (delete colliding backup keys first), delete store rows, bulk insert, neutralize additional rows, set `IsOffer` if any non-transfer `PurchaseTrans.FreeQty > 0`. `OrderId` is `YYYYMMDDHHMMSS`. One running job per store (409). Jobs are in-memory and lost on process restart (`service.py` header comment).

### L-10 Qty Review vs later edit

| Action | Effect | Evidence |
|---|---|---|
| `PATCH /qty-check/{store}/{code}` | Sets `orderqty`, `qtycheck=1`. Qty 0 → remarks `Don't Want to Order` | `repository.update_qty_check` |
| `PATCH /orders/{store}/{code}` | Sets `OrderQty` only. Qty 0 → `No Need - Reviewed`. Does **not** set `qtycheck` | `update_order_qty` |
| Reset pending | Unassigned latest order restored from `OrgOrderQty`; assigned stay reviewed | `repository` reset-pending |

Pydantic `order_qty: int` only. **No server max, pack multiple, or negative rejection beyond int typing.**

### L-11 Grids

- Qty Review: `qtycheck=0 AND status=0`
- Pending: `qtycheck=1 AND status=0` (zero-qty “no need” still listed)
- Columns are stored order fields plus last offer `OUTER APPLY` on `PurchaseTrans`

### L-12 History panels

On product select, web loads order history, purchase/GRN (top purchases), sales/bill detail, monthly stats. `mode=local` reads central; `remote` reads branch. Monthly chart nets returns rather than adding them twice (`repository` monthly-stats comments).

### L-13 Supplier, export, close

- Assign toggles status 0↔1 and copies `orderqty` into the supplier quantity. Status 2 untouched.
- One assignment path per line in the toggle model (not a split allocator).
- Export: if `product_codes` passed, bulk-assign those then export assigned rows; else export **already assigned** rows (`order_export.py`).
- **Undocumented:** web By Supplier export calls export **without** `product_codes` (`OrderWorkspacePage.tsx` ~383; `legacyOrderService.ts`). Desktop passes `product_codes` (`App.jsx` ~4318). Web help text that says export assigns the filtered stock-eligible set does not match the API call.
- Finalize requires no qty-pending and no unassigned lines with qty. Reopen returns workflow to ready.
- **Undocumented:** `ExportGenerationFailed` text says assignments were not changed, but bulk assign runs before the workbook is built.

### L-14 Compare previous order

`POST /compare-previous-order` applies backup rules: carry forward assigned lines, mark processed, zero reviewed, and reduce qty when backup stock is higher than current stock (`OrderQty = OrgOrderQty − sold delta`). This is a **second** quantity mutation after generation. Nexora has no equivalent.

### L-15 Offer flag

`IsOffer` is informational (free qty seen on a non-`TI` purchase). It does not change `OrderQty`.

---

## 4. Nexora procurement rule inventory

Authoritative engine: `decision_rules.py`. Input SQL: `decision_repository.load_source`. Narrative that matches this code: `docs/Nexora_Demand_Generation_Rules.md`. Older flow/catalogue docs do **not** match and must not be used as the spec.

### N-01 Cycle and refresh

One active cycle per tenant+store (`orchestration_service.py`). A refresh runs generation, builds working items, carries forward skips/pending, archives the previous refresh. Workspace selection is `cycle_id` + `refresh_id`. Closed cycle or closed refresh is read-only in the page.

### N-02 Sales inputs

Retail lines only: `SeriesTransID=1`, validity 0, `DontConsiderInOrder=0`, `TransactionDate >= today − rolling_days` (refresh parameter, default 90).

| Metric | Definition |
|---|---|
| `window_sales_qty` | SUM(qty) |
| `billing_frequency` | COUNT DISTINCT bill key (series\|bill\|date) |
| `max_day_sale_qty` | MAX of per-day sums |
| `max_bill_qty` | MAX of per-bill sums |
| `max_line_sale_qty` | MAX single row qty |
| `current_stock` | latest-month `ProductTrans.StockInHand`, fallback `Products.TotalStock`, else 0 |
| `last_sale_date` | MAX sale `TransactionDate` (full history, valid retail) |
| `last_received_date` | MAX `PurchaseTrans.grndate` |
| pending / in-transit / reserved | **not selected; evaluate defaults 0** |
| `dont_consider` | **hard-coded `CAST(0 AS BIT)`** in `load_source` (~156). The Python exclusion exists but this loader never sets it. Line-level `DontConsiderInOrder` still drops those sales from the window. |

### N-03 Terminal exclusions (in order)

1. Inactive → `EXCLUDED_INACTIVE` (SQL already filters `isActive=1`, so this is defensive).
2. `dont_consider` → `EXCLUDED_FLAGGED` (unreachable with current loader).
3. `AvgDailySales <= 0` → `EXCLUDED_NOT_SELLING`.
4. No sale in `recency_days` (default **10**) → `EXCLUDED_STALE_SALE`.
5. GRN exists and `last_sale < last_recv` → `EXCLUDED_RECENTLY_RECEIVED`. Same-day sale is kept.
6. Neither `DaysCover < MinDays` nor `EffectiveAvailable < MinQtyFloor` → normally `EXCLUDED_ADEQUATE_COVER`.
7. Exception 6a: `eff <= 1 AND MinQtyFloor <= 1 AND billing_frequency > 1 AND window_sales_qty > 1` → **INCLUDE `suggested_qty = 1`** (`INCLUDED_RARE_MOVER_TOPUP`).
8. After sizing, loose qty `<= 0` → `EXCLUDED_ZERO_REQUIRED`.

`MinQtyFloor = MAX(CEIL(AvgDailySales×MinDays), CEIL(window_sales_qty/billing_frequency))`.

Only `INCLUDE` rows are written to the VPL (`decision_service.py`). Excluded products are counted, not stored. Decision Flow “persist exclusions” is **not** what the code does.

### N-04 Suggested quantity

```
AvgDailySales     = window_sales_qty / rolling_days
EffectiveAvailable = max(0, stock + pending_receivable + in_transit − reserved)  # pending terms 0 today
TargetStock       = AvgDailySales × MaxDays          # not pre-rounded
GrossTarget       = MAX(TargetStock, max_day, max_bill, max_line)
Required          = GrossTarget − EffectiveAvailable
Loose             = max(0, CEILING(Required))
Suggested packs   = CEILING(Loose / SaleUnit) if SaleUnit > 0 else Loose
```

`final_required` in `decision_rules.py` ~156–205. Working items seed `final_qty = suggested_qty`, `assigned_qty = 0`, `remaining_qty = suggested_qty`, `item_status = draft`.

### N-05 Buyer quantity and states

| Status | Meaning |
|---|---|
| `draft` | Generated, not saved by buyer |
| `review` | `set_final_qty` saved; `remaining = final − assigned` |
| `skipped` | final 0, skip reason required (`current_refresh` / `until_next_sales` / `until_next_demand`) |
| `deferred` | excluded from bulk auto-assign; qty unchanged |
| assigned / partial | assignment recompute (inferred from status strings used by UI) |

UI “planning state” is derived, not a separate approval role: skipped / assigned / deferred / finalized (reviewed qty > 0) / pending. **No approver gate.**

Override sets `manual_override` and reason. Restore returns suggested and `draft`.

### N-06 Supplier

Recommendations: purchase-history queue, frontend re-rank in `purchaseValue.ts` (mapping 100, last purchase 40, frequency 30, PTR 20, live stock 10), display cap 8. Auto-assign uses the same weights. `assignment_service`: qty > 0, sum ≤ `final_qty`, **one active supplier per item** (409 if a different supplier is already active). Skipped blocked. Exported assignments cannot change supplier. Schemes/free/discount display on supplier stock; **they do not change suggested qty**.

### N-07 Export, pending, GRN

Export stamps draft assignments into a batch and marks them exported. Pending is `remaining_qty > 0`. GRN reconciliation is `reconciliation_rules.py` plus workspace GRN submit. Cycle close is a separate orchestration step. Network movement cache is computed after refresh on a background thread (comment ~230s) and does not change suggested qty.

### N-08 Load shape

Workspace loads up to 5000 rows, bulk supplier recommendations, and aborts superseded fetches (`PurchaseWorkspacePage.tsx`). Product intelligence (sales/purchase history) loads in `DetailColumn` when a product is selected. Decision trace loads only from the product info dialog. **No frontend unit tests** for `ProductGrid` or the workspace page. Engine tests: `tests/test_procurement_decision_engine.py` (including PARA-500: 130 loose → 13 strips at sale unit 10).

---

## 5. Common rules comparison matrix

| ID | Rule | Legacy | Nexora | Agreement |
|---|---|---|---|---|
| RULE-001 | Retail sales only, valid, not dont-consider-in-order | L-01 | N-02 | Equivalent purpose. Frequency key differs (RULE-014). |
| RULE-002 | Inactive products out | `isactive = 1` | SQL `isActive=1` | Equivalent for generation. |
| RULE-003 | Rolling demand window default 90 days | Hard-coded `@ODATA` and `/90.0` | `rolling_days` default 90 | Equivalent at default. Nexora can change the window; legacy’s divisor stays 90 even if `@ODATA` were changed. |
| RULE-004 | Min/max day cover parameters | Default 13/18, caller may override; warehouse 32/35 | Per refresh | Equivalent purpose. Warehouse profile absent in Nexora. |
| RULE-005 | Per-bill (or per-line) floor inside min qty | `CEIL(slsqty/Frequence)` | `CEIL(window/billing_frequency)` | Same shape, **different frequency grain** (CONFLICT-004). |
| RULE-006 | Order in sale-unit packs via CEILING | L-04 | N-04 | Same operator. Inputs differ so results differ (CONFLICT-002). For integer stock and a single pre-ceiled gross target, the two ceiling orders match. |
| RULE-007 | Do not order if no sale inside recency | L-03 | N-03 step 4 | Same purpose, **different N and different date source** (CONFLICT-001). |
| RULE-008 | Do not order if nothing sold since last receipt | `lastsaledate >= LastReceivedDate` | `last_sale < last_recv` excludes | Same intent. Date sources differ (ProductTrans vs PSI / PurchaseTrans). Additional-row branch uses strict `>`. |
| RULE-009 | Zero buyer qty means do not order this line | Qty-check remarks; status path | Skip, `final_qty=0` | Equivalent purpose, different persistence (CONFLICT-006). |
| RULE-010 | Pack size from product `SaleUnit` | SQL | `Products.SaleUnit` | Equivalent field. `SaleUnit<=0` → legacy qty 0 (unless the zero-stock edge returns 1); Nexora falls back to loose units. |
| RULE-011 | Offer / free qty is visible, not a demand input | `IsOffer` | Supplier-stock badge | Equivalent purpose. |
| RULE-012 | Store-scoped generation | `StoreName` / branch DB | `tenant_id+store_id` | Equivalent purpose, different databases. |
| RULE-013 | Buyer can override generated qty | PATCH | `set_final_qty` | Equivalent purpose. Legacy has two PATCH semantics (L-10). |
| RULE-014 | “Frequency” | `COUNT(DISTINCT ProductSaleInformation.ID)` | Distinct bill key | **Conflict.** If `ID` is a line key, multi-line bills inflate legacy frequency and shrink the per-bill floor. |

---

## 6. Legacy-only rules matrix

| ID | Rule | Recommendation |
|---|---|---|
| RULE-101 | Additional Row inserted then **zeroed** (L-06) | Do not copy the zeroing bug-as-feature into Nexora without a decision. See CONFLICT-003. Preserve as an explicit exclusion reason if the business wants those SKUs **off** the order. |
| RULE-102 | WantedType classification strings | Optional column, not a quantity. Useful as the “why” chip. Do not let the label drive math. |
| RULE-103 | `OrgOrderQty` + reset pending to original | **Preserve.** Nexora restore-to-suggested is the analogue; legacy also restores after a partial review. Unified model needs “generated qty” immutable. |
| RULE-104 | Compare-to-previous-order stock delta (`OrgOrderQty − sold`) | **Business decision.** It changes qty using a backup snapshot. Not in Nexora. Do not enable until an owner confirms it is still wanted. |
| RULE-105 | Local vs remote generation target (central vs branch DB) | **Retain as a data-source mode**, not a second formula. Nexora already reads `sync.*`. Branch-live remote mode matters only where sync lag is unacceptable. |
| RULE-106 | Warehouse / transfer-out demand, recency 30, min/max 32/35 | **Preserve as a store profile.** Nexora engine has no warehouse demand definition. Blocked until `order_warehouse.sql` is extracted. |
| RULE-107 | NMW/HO stock refresh into `SupplierStock` before retail generation | **Optional pre-step** for supplier availability, not for suggested qty. Failures are logged and generation continues (`order_process.py` ~458). |
| RULE-108 | Qty-check flag (`qtycheck`) separate from order qty | **Preserve the two-phase review** (unreviewed vs reviewed). Nexora `draft` vs `review` is the mapping. |
| RULE-109 | Workflow finalize blocked while unassigned qty remains | **Preserve.** Nexora export does not use this exact gate; assignment can be partial via `remaining_qty`. |
| RULE-110 | Desktop export passes `product_codes` (bulk assign); web export does not | **Bug, not a rule.** Unified export must assign only what the user included, in one transaction, or export only pre-assigned rows — and the UI must say which. |
| RULE-111 | Header watermarks (last bill, last GRN number) | Display only. Load with store context, not per product. |
| RULE-112 | In-memory order job, lost on restart | **Reject as the unified design.** Keep the legacy behavior until replaced; new model persists refresh state (Nexora already does). |

---

## 7. Nexora-only rules matrix

| ID | Rule | Recommendation |
|---|---|---|
| RULE-201 | Days-cover OR min-qty qualification | Keep the min-qty floor (legacy). Days-cover is largely implied by that floor when stock and average match (see §9). Do not advertise it as an independent order increase. |
| RULE-202 | Gross target includes **max day sum** and **max bill sum** | **Conflict.** Stronger than legacy. Owner must opt in (CONFLICT-002). |
| RULE-203 | `MaxLineSaleQty` as a gross-target term | This is the legacy spike. **Keep.** |
| RULE-204 | Rare-mover **include qty 1** | **Conflict** with L-06 zeroing (CONFLICT-003). |
| RULE-205 | Movement class and stock status | Keep as labels. They must not change qty. |
| RULE-206 | Reason codes / trigger determinant | **Keep.** This is the audit trail legacy WantedType only partly covers. |
| RULE-207 | VPL include-only persistence | Accept for the working list. Exclusions need a side log if buyers must see “why not on the order”. Not required for v1 of the compact grid. |
| RULE-208 | `final_qty` separate from `suggested_qty`, `assigned_qty`, `remaining_qty` | **Keep.** This is the correct quantity split. Legacy overloads `OrderQty`. |
| RULE-209 | Single active supplier per line; no split | **Keep** unless purchasing explicitly wants split POs. Legacy toggle is also one supplier at a time. |
| RULE-210 | Skip modes that carry forward across refresh | **Keep.** Legacy has no equivalent; it is an operational safeguard. |
| RULE-211 | Defer (hold qty, skip auto-assign) | **Keep** as optional. Not on the first keyboard path. |
| RULE-212 | Weighted supplier score and auto-assign | **Keep** behind an explicit action. Do not auto-run on grid load. |
| RULE-213 | Export batch + GRN reconciliation + cycle close | **Keep** as the downstream of the unified workspace. |
| RULE-214 | Network movement class on the row | Optional column. Must not block first paint (it is already async and slow). |
| RULE-215 | Read-only when cycle/refresh closed | **Keep.** |
| RULE-216 | Product-level `dont_consider` exclusion | Engine supports it; loader forces 0. **Wire the real flag** if the product master has one. Until then, do not claim the rule is active. |
| RULE-217 | Effective available includes pending PO / transit / reserved | Formula exists; inputs are 0. **Do not fake.** Enable only when a synced source exists. |

---

## 8. Rules missing from both

| ID | Gap | Necessity | Risk if ignored | Acceptance |
|---|---|---|---|---|
| RULE-301 | Stale snapshot detection (stock/sales as-of shown to the buyer) | High | Order against yesterday’s stock | UI shows source timestamp; refresh refuses if sync older than an agreed SLA |
| RULE-302 | Invalid master: missing name, `SaleUnit <= 0`, negative stock | High | Silent 0 qty or loose-unit fallback | Row flagged; not exportable until fixed or explicitly overridden |
| RULE-303 | Zero-history / new products | Medium | Invisible to both engines (no sales → out) | Separate “new product” list, not forced into the formula |
| RULE-304 | Duplicate demand (same product, two codes) | High | Double order | Canonical identity = store + product code. Cross-code dupes need a master map that **does not exist** in either engine. Blocked on master data. |
| RULE-305 | Negative, fractional, excessive qty | High | Legacy accepts any int; Nexora numeric grid is only partly guarded | Server rejects `< 0` and non-integers; warn above a multiple of suggested (threshold = owner) |
| RULE-306 | Assignment sum > approved qty | Medium in Nexora (409). Legacy copies order qty on assign | Over-ship | Keep Nexora guard |
| RULE-307 | Concurrent editors / stale row version | High | Last write wins, no version column found in the paths read | Optimistic version on `final_qty` / `OrderQty` update. **Not implemented in either system** (not fully proven for every legacy UPDATE). |
| RULE-308 | Partial export failure after assign | High on legacy (assign then Excel) | Rows assigned, file missing, message says otherwise | Single transaction: assign + export marker, or export only already-assigned |
| RULE-309 | Recovery after restart | Legacy jobs lost; Nexora refresh rows survive | Operator re-runs generation and replaces the order | Persist job state; never delete a reviewed order without backup (legacy backup exists; Nexora refresh archive exists) |
| RULE-310 | Auditable override | Nexora has override fields. Legacy remarks are a string | Cannot explain a qty | Require reason when qty ≠ suggested |
| RULE-311 | Failed source (branch down, sync empty) | Legacy 503; Nexora empty grid possible | Buyer orders from blank/wrong store | Hard error, no silent empty success |
| RULE-312 | Pending purchase reducing demand | Documented gap both sides | Double order against open PO | Only after a real pending source (RULE-217) |

None of RULE-301–312 should be coded as part of this audit.

---

## 9. Conflicting rules and required decisions

### CONFLICT-001 — Recency window and date source

| | |
|---|---|
| ID | CONFLICT-001 |
| Legacy | Include only if ProductTrans `LastBillDate` (joined only inside the recency window) is `>= today − 15` days (retail default). |
| Nexora | Exclude if PSI `MAX(TransactionDate)` is null or `< now − 10` days. |
| Example | Last real sale 12 days ago, stock below min, otherwise eligible. Legacy: **on the order**. Nexora: **`EXCLUDED_STALE_SALE`**. |
| Why | Different constants (`service.py` 15 vs `DecisionParameters.recency_days` 10) and different clocks (ProductTrans vs sale lines). `decision_rules.py` comment says “legacy: today−10”, which **disagrees with the legacy service default**. |
| Which is correct | **Not determinable from code.** |
| Decision | **BLOCKED FOR BUSINESS DECISION.** Choose N days and the date source. |
| Recommended unified rule | Use transaction-level last sale (Nexora source, it can see inside a month) and make N a store parameter. Default N = **15** until the owner says 10. Do not leave the comment and the constant in conflict. |
| Migration risk | Switching 10→15 adds SKUs; 15→10 drops SKUs that legacy buyers expect. |
| Regression test | Fixture last-sale at day 9, 12, and 16 for both date sources. |

### CONFLICT-002 — What the gross target is

| | |
|---|---|
| ID | CONFLICT-002 |
| Legacy | `maxqty = MAX(CEILING((slsqty/90)*MaxDays), Max single-line qty)`. Order `CEILING((maxqty − TotalStock) / SaleUnit)`. |
| Nexora | `GrossTarget = MAX(Avg×MaxDays, max day sum, max bill sum, max line)`. Packs `CEILING(CEILING(GrossTarget − stock) / SaleUnit)`. |
| Example | 90-day sales 180, 4 bills, max line 20, max day 80, max bill 60, stock 30, pack 10, min 13, max 18. Legacy `maxqty = MAX(36, 20) = 36`, order `CEILING(6/10) = 1` pack. Nexora gross `MAX(36, 80, 60, 20) = 80`, loose 50, **5 packs**. |
| Why | Nexora added day-sum and bill-sum as extra stock-level floors. Legacy never had them. |
| Which is correct | **Not determinable.** Nexora authors documented them as stronger safeguards, not as a measured match to VB. |
| Decision | **BLOCKED FOR BUSINESS DECISION.** |
| Recommended unified rule | **Legacy spike only** (cover target and max line) as the default generation profile, because that is the quantity pharmacies have been receiving. Expose max-day and max-bill as an **opt-in profile**, not a silent replacement. |
| Migration risk | Opt-in later increases orders on spiky items. Silent Nexora default over-orders versus current legacy stores. |
| Regression test | The numeric example above, plus PARA-500 (`tests/test_procurement_decision_engine.py`) so the pack ceiling itself does not regress. |

### CONFLICT-003 — Rare mover / Additional Row

| | |
|---|---|
| ID | CONFLICT-003 |
| Legacy | Union inserts qty 1, then update sets qty 0, `Status=2`, remarks `Additional`. Line is not in Qty Review (`status=0`). |
| Nexora | Same predicates (stock≤1, floor≤1, frequency>1, sales>1) **include suggested_qty = 1**. |
| Example | Stock 1, min qty floor 1, sold 3 units on 3 bills, sold after GRN. Legacy orderable qty **0**. Nexora working item **1**. |
| Why | Nexora treated the pre-zero SQL qty as the business rule. The post-step in `order_process.py` is the behavior buyers see. |
| Which is correct | **Legacy runtime result is what production does today.** Whether zeroing was intentional is **not proven** (no comment says “hide these”). |
| Decision | **BLOCKED FOR BUSINESS DECISION.** |
| Recommended unified rule | Until the owner says otherwise, **do not put these SKUs on the order** (match the post-update). Record reason `ADDITIONAL_ROW_NEUTRALIZED` so they can be turned on later. |
| Migration risk | Keeping Nexora’s 1-pack adds a long tail of slow movers. |
| Regression test | One fixture that is additional-row-only; assert orderable qty 0 under the legacy profile. |

### CONFLICT-004 — Frequency grain and min floor

| | |
|---|---|
| ID | CONFLICT-004 |
| Legacy | `Frequence = COUNT(DISTINCT ps.ID)` |
| Nexora | Distinct bill key |
| Example | One bill, three sale lines, qty 10+10+10. Legacy frequency 3, per-line average 10. Nexora frequency 1, per-bill average 30. Min floor can jump from 10 to 30 and pull the product onto the order. |
| Why | Different GROUP keys. Schema was not re-proven in this audit beyond the SQL text. Inferred: `ID` is the sale-line identity. |
| Which is correct | **BLOCKED** if the business defines “average per bill”. If the business defines “average per sale line”, legacy is the match. |
| Recommended unified rule | Count **bills** (Nexora) only after one store sample confirms `ID` is not already one row per bill. Until then, legacy profile uses `COUNT(DISTINCT ID)`. |
| Migration risk | Bill-level frequency raises the floor and adds lumpy items. |
| Regression test | Multi-line single bill fixture. |

### CONFLICT-005 — Stock column

| | |
|---|---|
| ID | CONFLICT-005 |
| Legacy | `products.TotalStock` at generation |
| Nexora | Latest-month `ProductTrans.StockInHand`, else TotalStock, else 0. `docs/Nexora_Demand_Generation_Rules.md` records an owner ruling (2026-07-15) that TotalStock was wrong for ~26% of one store and must not be reverted casually. |
| Example | Not re-measured here. Any product where the two columns differ changes min-gate and order qty by `CEILING(delta / SaleUnit)`. |
| Why | Different columns. |
| Which is correct | **Prior ruling says StockInHand.** This audit did not re-sample the 26%. |
| Decision | Treat StockInHand as the Nexora ruling. **Reconfirm** before a legacy store is switched, because quantities will move. |
| Recommended unified rule | `current_stock = StockInHand` with TotalStock shown as a secondary figure when they differ by more than one pack. Do not average them. |
| Migration risk | High on first cutover of a live legacy store. |
| Regression test | Pair of products: columns equal; columns differ by 25 units. |

### CONFLICT-006 — Zero quantity and keyboard commit

| | |
|---|---|
| ID | CONFLICT-006 |
| Legacy web Qty Review | Enter saves current qty via qty-check (removes from unreviewed). Esc saves **0**. Arrows move **without** save. |
| Legacy desktop Qty Check | Arrows **commit**. Enter calls qty-check (which **always** sets `qtycheck=1`, despite comments that say otherwise). Esc/empty Backspace commits 0. |
| Nexora ProductGrid | Enter and ArrowDown save; qty 0 skips. ArrowUp moves without save. Esc skips (qty 0) and **does not advance**. Space toggles export checkbox, not defer. |
| Example | User presses Down on an unreviewed row. Web legacy: selection moves, qty unchanged. Desktop legacy: qty saved and marked reviewed. Nexora: qty saved/skipped and next row focused. |
| Why | Three implementations. |
| Which is correct | Web legacy matches its on-screen hint (`Enter Accept / Esc No need / ↑↓ Navigate`). Desktop and Nexora both commit on vertical move, which is faster and easier to mis-key. |
| Decision | **BLOCKED** only for Down-commits. Esc = do-not-order is shared and should stay. |
| Recommended unified rule | **Enter commits and advances. Esc sets do-not-order and advances** (legacy web Esc). **Up/Down move without commit** (legacy web). Nexora’s Down=save is dropped so a navigation key cannot skip a product. |
| Migration risk | Buyers trained on Nexora Down-to-save will under-save until the hint is visible. |
| Regression test | Keyboard matrix in §15. |

### CONFLICT-007 — Eligibility when min floor exceeds max target

| | |
|---|---|
| ID | CONFLICT-007 |
| Legacy | Needs **both** `minqty > stock` and `(maxqty − stock)/SaleUnit > 0`. A high per-frequency floor with a low max line can fail the second test and drop the line. |
| Nexora | Qualifies on `stock < MinQtyFloor` even when cover target and max line are below stock, then may still order if max day/bill lift the gross target. |
| Example | min floor 45, max line 20, days target 36, stock 42, and max day/bill also ≤ 42. Legacy: **out** (`maxqty <= stock`). Nexora: qualifies (`42 < 45`) then `EXCLUDED_ZERO_REQUIRED` if gross ≤ 42. If max bill is 50, Nexora orders and legacy does not. |
| Why | Extra AND in legacy SQL; extra gross terms in Nexora. |
| Decision | Covered by CONFLICT-002 for the spike terms. The extra AND should remain in the legacy profile. |
| Recommended unified rule | Legacy profile keeps both predicates. |
| Regression test | Stock between max line and per-bill floor. |

### CONFLICT-008 — Web vs desktop export assign

Not a formula conflict. Web export does not send `product_codes`; desktop does. Unified rule: export the rows the user marked, and do not assign as a side effect unless the button says Assign and export. See RULE-110.

---

## 10. Evidence index

| Topic | Location |
|---|---|
| Legacy SQL formulas | `backend/modules/legacy_order/sql/order_local.sql` (one statement; min/max, WantedType, Orderqty, WHERE, Additional Row UNION) |
| Legacy bind + additional zero + IsOffer | `backend/modules/legacy_order/order_process.py` ~140–160, ~227–253, ~412–469 |
| Legacy defaults | `backend/modules/legacy_order/service.py` ~23–39 |
| Legacy qty PATCH | `backend/modules/legacy_order/repository.py` `update_qty_check`, `update_order_qty` |
| Legacy export | `backend/modules/legacy_order/order_export.py` |
| Web workspace keys | `frontend/src/pages/legacy-order/OrderWorkspacePage.tsx` ~309–427, ~611 |
| Desktop workspace keys | `desktop/supplier-stock-client/src/App.jsx` OrderWorkspace qty handlers ~4122–4166 and supplier keys ~4826–4841 |
| Nexora formulas | `backend/modules/procurement/decision_rules.py` `average_daily_sales`, `min_qty_floor`, `final_required`, `evaluate` |
| Nexora inputs | `backend/modules/procurement/decision_repository.py` `load_source` |
| Nexora assign guard | `backend/modules/procurement/assignment_service.py` ~66–92 |
| Nexora keyboard | `frontend/src/components/procurement/ProductGrid.tsx` ~278–398 |
| Nexora demand doc (aligned) | `docs/Nexora_Demand_Generation_Rules.md` |
| Nexora docs (stale) | `docs/Procurement_Decision_Flow.md`, `docs/Procurement_Business_Rules.md`, `docs/BUSINESS_RULES/PR-BR-001-90-day-average.md`, `PR-BR-002-min-day-rule.md` |
| Engine tests | `tests/test_procurement_decision_engine.py` |
| Legacy workflow tests | `tests/test_legacy_order_workflow.py` |
| Legacy auth tests | `backend/tests/test_legacy_order_store_access.py` |
| Offer perf note (77s, 1385 rows) | `order_process.py` ~234–239; migrations `0005`, `0006`, `0007` under `backend/modules/legacy_order/sql/` |

**Tests that do not exist:** frontend tests for either workspace keyboard; a test that executes `order_local.sql` against fixtures; a test that compares legacy SQL output to `decision_rules.evaluate` on the same inputs.

**Not claimed:** formulas were not executed against OrderNMC in this audit. PARA-500 is a unit test of Nexora’s Python function only.

---

## 11. Unified business-rule specification (proposed, not approved)

Two profiles. **No blended formula.**

### Profile L — legacy retail (default until CONFLICT-002 is explicitly accepted)

Inputs, per store + product, frozen at generation:

- `window_qty`, `line_frequency` (`COUNT DISTINCT sale-line id`), `max_line_qty`, `total_stock` **or** the stock field from CONFLICT-005 once reconfirmed, `sale_unit`, `last_sale`, `last_grn`
- Parameters: `min_days`, `max_days`, `recency_days` (default 15), window 90

```
min_loose = MAX(CEILING(window_qty/90 * min_days), CEILING(window_qty/line_frequency))
max_loose = MAX(CEILING(window_qty/90 * max_days), max_line_qty)
eligible  = last_sale within recency
            AND last_sale >= last_grn
            AND min_loose > stock
            AND sale_unit > 0
            AND (max_loose - stock) / sale_unit > 0
suggested_packs = CEILING((max_loose - stock) / sale_unit)
```

Additional-row predicate: **record and exclude** (qty 0) until CONFLICT-003 is reversed.

### Profile N — current Nexora engine

Unchanged `decision_rules.evaluate`. Used only when the owner accepts CONFLICT-002 and CONFLICT-001 as specified in code today.

### Shared, profile-independent

1. Generated suggestion is immutable.
2. Buyer `final_qty` is the only orderable quantity. `0` means do not order, with a reason.
3. `assigned_qty` ≤ `final_qty`. One supplier per line.
4. `exported_qty` is what the file contained. `received_qty` comes only from GRN match. `pending = final − received` on exported lines (Nexora remaining model), never a rewrite of `final_qty`.
5. Offers do not change suggestion or final qty.
6. Warehouse stores stay on the legacy warehouse SQL until that formula is written down the same way. They are not run through Profile L retail.

---

## 12. Proposed order lifecycle and states

```
Store selected
  → data-as-of checked (RULE-301, later)
  → Refresh / Generate (Profile L or N)
  → lines in UNREVIEWED (suggestion copied to final)
  → buyer Enter: REVIEWED (final > 0) or DECLINED (final = 0)
  → optional supplier assign (ASSIGNED) while assigned_qty = final_qty
  → export (EXPORTED) only for assigned included lines
  → GRN (PARTIAL_RECEIPT | RECEIVED)
  → cycle close archives the refresh
```

Interrupted generation: if the job dies, the previous `OrderManagement` backup (legacy) or previous refresh (Nexora) remains the last good order. A new generate must not delete reviewed lines without writing the backup first (legacy already does this inside one transaction).

**Identity:** `(store, refresh_or_order_id, product_code)`. Duplicate detection is that key. The same product on two suppliers is forbidden (RULE-209). The same product in two open refreshes for one store is forbidden by “one active working refresh” (already Nexora’s active-cycle rule). Cross-store demand is not consolidated.

---

## 13. Proposed domain / data flow

| Stage | Inputs | Outputs | Failure |
|---|---|---|---|
| 1. Store session | User store rights | `store_id`, profile L or N, as-of | 403 / empty store list |
| 2. Eligibility | Master + sales + stock | Include/exclude + reason | Source down → error, clear grid |
| 3. Suggestion | Eligible metrics | `suggested_packs` | `SaleUnit<=0` → blocked row, not a silent 0 |
| 4. Final qty | Suggestion + keystroke | `final_qty`, reason if override or zero | Save failure → keep edit, stay on row |
| 5. Assign | Final qty + supplier | `assigned_qty` | 409 if second supplier or qty overflow |
| 6. Export | Assigned lines | File + exported marker | No marker if file fails |
| 7. Receipt | GRN lines | `received_qty`, pending | Unmatched GRN stays in reconciliation, does not change suggestion |

Raw source, suggestion, final, assigned, exported, received, and pending are separate fields. UI “order qty” edits **final** only.

---

## 14. Proposed component tree and compact layout

**Viewport:** 1366×768, minus browser/Electron chrome and taskbar. Design to about **1280×640** of usable workspace, not 1366×768 of content.

Reuse: `ProductGrid` keyboard model (after CONFLICT-006), `purchase-manager.css`, legacy `ProductDetailPanel` data hooks (`monthly-stats`, purchase, sales). Do not mount both full screens.

```
OrderWorkspacePage
  WorkspaceHeader          store, refresh/order id, profile, sync as-of, error
  FilterBar                search, product type, review state, wanted/reason (one row)
  WorkspaceBody
    ProductGrid            virtualized when row count > ~200 (already a TODO at 2000)
    DetailDrawer           tabs: Trend | Purchases | Decisions | Bills
  ActionBar                Assign | Decline | Export | Finalize — disabled when invalid
```

### Header (~40px)

Store name, order/refresh id, mode (Review / Assign), one-line status (loading, stale request discarded, last error + Retry).

### Grid columns (default)

Only fields that change the buy decision:

| Column | Width intent | Source |
|---|---|---|
| # | 36 | row index |
| Product | flex | name |
| Offer | 36 | icon if `IsOffer` or supplier scheme, empty otherwise |
| Order | 64 | **final qty**, the only editor |
| Stock | 56 | stock used by the profile |
| Pack | 48 | sale unit |
| Sales | 56 | window qty |
| MRP | 64 | display |
| Last GRN | 72 | date |
| Status | 72 | unreviewed / reviewed / declined / assigned |

Suggested qty is a ghost value inside the Order cell (or a tooltip), not a second input. WantedType/reason is on the detail drawer, not a default column. Max qty, last sale, and txn date move to the drawer. Column chooser is not in v1.

### Detail drawer (~220px, collapsible)

One tab visible. Default **Trend** (monthly). Purchases and bills load on first open of that tab, not on row change for every tab. Changing row clears the drawer immediately and reloads the active tab only.

### Action bar (~36px)

Review mode: no Assign button. Assign mode: Assign enabled only when a supplier is highlighted and `final_qty > 0` and line is not declined. Export enabled only when at least one assigned line is included. Finalize uses the legacy gate (no unassigned positive qty) **if** the owner keeps RULE-109.

### 1366×768 fit

Header 40 + filter 36 + action 36 + drawer 220 + grid chrome ~28 ≈ 360px chrome. Remaining grid height ≈ 280px → about **9–11 rows** at 28px row height. That is acceptable only because the drawer collapses to a 28px strip (grid then ≈ 14–16 rows). Default: drawer **collapsed** until the user opens it or presses the detail shortcut. This is a deliberate change from both screenshots, which show too many panels for this height.

---

## 15. Keyboard-navigation contract

**Adopted only after CONFLICT-006 is accepted as recommended.** Until then this is a proposal.

| Key | Qty cell, editing | Qty cell, not editing | Supplier zone | Drawer collapsed |
|---|---|---|---|---|
| ↑ | Move to previous row, **no save** | Same | Previous supplier; from first supplier → qty cell | Previous row |
| ↓ | Next row, **no save** | Same | Next supplier | Next row |
| Enter | Commit valid qty, advance | Commit current qty, advance | Assign highlighted supplier for full `final_qty`, advance product, return to qty | Commit qty if the grid has focus |
| Esc | Cancel in-cell edit back to last saved | Decline (qty 0) **and advance** | Leave supplier zone, no assign | Close drawer if it has focus, else decline |
| Tab / Shift+Tab | Next / previous **editable** row | Same | Same | Skip hidden drawer controls |
| → | Move to supplier zone if assign mode and final > 0 | Same | — | Open drawer |
| ← | — | — | Back to qty, no assign | Close drawer |
| Ctrl/Cmd+F | Focus search | Focus search | Focus search | Focus search |
| F2 | Edit qty | Edit qty | — | — |
| Space | **No export toggle while typing a number** | Toggle include-for-export only in assign/export mode | — | — |

**Qty 0 on Enter:** decline, same as Esc, advance.  
**Invalid (negative, blank, decimal):** do not call the API; leave the cell in error; do not advance.  
**Save failure:** stay on the row, show the error in the header, keep the typed value.  
**First/last row:** ↑ on first and ↓ on last do nothing. Enter on last commits and focus stays.  
**Filter change:** clear selection if the active product is hidden; otherwise keep it. Do not commit a half-typed qty (cancel the edit).  
**Active product disappears** (another user or refresh): clear detail, select the nearest remaining index, discard unmatched responses.  
**Collapsed drawer:** ←/→ still open it; detail fetches do not run while collapsed.  
**Destructive:** Finalize and Export are not single unmodified keys. No shortcut without a focused button or an explicit chord that the action bar shows. Esc never finalizes.  
**Discoverability:** one hint line under the filter bar, matching the mode. Focus ring uses the existing purchase-manager focus style.

Desktop `+`/`-` nudge may remain as a Stock Client extra. It is not part of the web contract.

---

## 16. Performance findings and measurements

### Measured in code comments (not re-timed here)

| Case | Evidence | Figure |
|---|---|---|
| Legacy qty grid `IsOffer` per row | `order_process.py` ~234–239, before migration 0007 | **77s** for 1385 order rows against ~278k `PurchaseTrans` rows; over the desktop 45s client timeout |
| Nexora network movement after refresh | `orchestration_service.py` comment | **~230s** background; must not block the grid |

### Not measured (profiling tasks — do these before optimizing)

| ID | What to time | How |
|---|---|---|
| P-1 | Legacy workspace first grid | One store, cold, Qty Review request only |
| P-2 | Legacy store switch | Time until old rows cleared and new first row selected |
| P-3 | Legacy detail | Three calls on select (purchase, sales, monthly) |
| P-4 | Nexora workspace | `GET workspace?page_size=5000` + recommendations |
| P-5 | Nexora qty save | `set_final_qty` and whether the page refetches the grid |
| P-6 | Generate | `order_local.sql` duration vs `generate_vpl` duration, same store |

### Design constraints (justified by the code, not by new timings)

1. Store change clears rows and detail **before** the request returns (web legacy already clears scoped state; keep that).
2. Every workspace request carries a monotonic generation; responses with an old generation are dropped (Nexora abort controllers exist; legacy desktop must get the same).
3. First row selected only after the **new** payload arrives.
4. Grid payload has no purchase/sales history. History is per selected product, active tab only.
5. Do not reload the grid after a successful qty save.
6. `LastOffer` `OUTER APPLY` on every qty-check load is still a per-row purchase probe (`repository` qty-check). Leave it until P-1 shows it dominates. IsOffer itself was already moved to generation time.
7. Virtualize the Nexora grid only if P-4 shows render, not SQL, is the cost. The page already notes 2000+ rows.
8. Do not cache stock across stores.

**Targets (goals, not measurements):** first order row visible < 2s on a typical store after sync data is local; qty save < 300ms; store switch shows empty grid within one frame; detail tab < 1s. Reject any change that hits the target with the previous store’s rows.

---

## 17. Regression and acceptance test matrix

Use `tests/test_procurement_decision_engine.py` and `tests/test_legacy_order_workflow.py`. Do not weaken them.

| Test | Proves | Status today |
|---|---|---|
| T-L1 Execute Profile L on a fixture equal to the SQL CASE | CONFLICT-002 legacy numbers | **Missing** |
| T-N1 PARA-500 and exclusion cases | Nexora engine unchanged | Present |
| T-C1 Recency day 9/12/16 | CONFLICT-001 | **Missing** |
| T-C2 Numeric example in CONFLICT-002 | Spike terms | **Missing** |
| T-C3 Additional-row fixture qty 0 vs 1 | CONFLICT-003 | **Missing** |
| T-C4 Multi-line one bill | CONFLICT-004 | **Missing** |
| T-C5 StockInHand ≠ TotalStock | CONFLICT-005 | **Missing** |
| T-Q1 SaleUnit 10, loose 130 → 13 | Pack ceiling | Present for Nexora |
| T-Q2 SaleUnit 0 | Blocked row, not loose fallback, under Profile L | **Missing** |
| T-Q3 Negative qty rejected | RULE-305 | **Missing** |
| T-A1 Second supplier 409 | RULE-209 | Present in assignment service tests if `test_procurement_pm_workflow.py` covers it — confirm during Phase 0, do not assume every case |
| T-E1 Export failure does not mark exported | RULE-308 | **Missing** for legacy (known message bug) |
| T-UI1 1280×640: header, one filter row, grid, no overlap | §14 | **Missing** (no frontend workspace tests) |
| T-UI2 Keyboard matrix §15 | CONFLICT-006 | **Missing** |
| T-UI3 Store switch drops old product in detail | §16 | **Missing** |
| T-P1 Save then reload final qty | Persistence | Backend workflow tests partial; UI **missing** |

---

## 18. Risks, unresolved questions, blocked decisions

**Blocked (must be answered before coding quantities):**

1. CONFLICT-001 recency N and date source.
2. CONFLICT-002 whether max-day and max-bill may increase qty.
3. CONFLICT-003 additional row on the order or neutralized.
4. CONFLICT-004 line frequency vs bill frequency.
5. CONFLICT-005 confirm StockInHand remains the stock input for stores that still order on TotalStock.
6. CONFLICT-006 Down commits or only moves.

**Unresolved, not blocking a written spec:**

- Full extract of `order_remote.sql` parity vs local (agent noted a `SaleUnit` NULLIF difference; not re-quoted here).
- Full extract of `order_warehouse.sql` before any warehouse store uses the new workspace.
- Whether `ProductSaleInformation.ID` is unique per line (inferred).
- Pending PO source (both systems ignore it).
- Web export bug (RULE-110) can be fixed inside legacy without the unified UI, but that **is** a production change and is out of this audit.

**Risks:**

- Building the compact UI on Nexora’s current engine will change live order quantities versus the Stock Client even if every column looks familiar.
- Averaging the two formulas is rejected.
- `docs/Procurement_Decision_Flow.md` will mislead the next implementer if treated as current.

---

## 19. Prioritized implementation phases

Each phase starts only after the previous acceptance criteria pass. **Phase 0 does not change buyer-visible qty.**

### Phase 0 — Golden harness

- **Scope:** Fixture runner for Profile L (SQL expression or a Python transcription tested against the SQL text) and Profile N (`evaluate`). No API change.
- **Depends on:** Blocked decisions recorded as profile flags, even if the flags stay “legacy”.
- **Files:** `tests/` only, plus a short expected-table beside this audit.
- **Acceptance:** T-L1, T-C1–T-C5, T-N1 green.
- **Rollback:** Delete the tests.

### Phase 1 — Generation profile switch

- **Scope:** Refresh parameter `profile=L|N`. Profile L calls the approved formula. Persist suggestion, reason, stock source, parameter snapshot.
- **Depends on:** Phase 0 and decisions 1–5.
- **Files:** `decision_rules.py`, `decision_repository.py`, `orchestration_service.py`, procurement tests. No legacy SQL edits.
- **Acceptance:** Same fixture as `order_local.sql` for Profile L; Profile N matches current `evaluate` byte for byte on existing tests.
- **Rollback:** Default profile remains N for current Purchase Manager stores; legacy stores stay on `legacy_order` until cutover.

### Phase 2 — Compact workspace shell

- **Scope:** New route composing header, filter row, grid, collapsed drawer. Wire existing workspace and legacy detail endpoints. Read-only first.
- **Depends on:** Phase 1 data shape.
- **Files:** `frontend/src/pages/procurement/` new components, `purchase-manager.css`. Do not delete `OrderWorkspacePage` or `PurchaseWorkspacePage`.
- **Acceptance:** T-UI1 at 1280×640; store switch clears rows; first row selected after load.
- **Rollback:** Route flag off; old pages remain.

### Phase 3 — Keyboard qty editing

- **Scope:** Contract in §15. Save final qty only. No grid reload.
- **Depends on:** Decision 6.
- **Files:** grid component, workspace save API.
- **Acceptance:** T-UI2, T-Q3, failed save stays on row.
- **Rollback:** Feature flag to previous ProductGrid key map for Nexora-only users.

### Phase 4 — Assign, export, finalize

- **Scope:** Single supplier, export without the legacy assign-then-fail hole, finalize gate.
- **Depends on:** Phase 3.
- **Files:** `assignment_service.py`, `export_service.py`, legacy export only if the desktop client is repointed.
- **Acceptance:** T-A1, T-E1.
- **Rollback:** Export stays on the old client until the new path matches a file diff on one store.

### Phase 5 — Cutover and retire duplicate chrome

- **Scope:** Point Stock Client order screen at the new route. Keep `legacy_order` generation until Profile L has matched a full store for one cycle.
- **Depends on:** One store parallel run.
- **Acceptance:** Buyer sign-off on qty diffs (should be empty under Profile L + agreed stock source).
- **Rollback:** Client config back to `OrderWorkspace`.

---

## 20. Go / no-go

**NO-GO** to implement the unified workspace or to change `decision_rules.py` / `order_local.sql` on the strength of this audit alone.

**GO** to:

1. Record owner answers for CONFLICT-001 through CONFLICT-006.
2. Start Phase 0 tests.
3. Fix documentation drift (`Procurement_Decision_Flow.md` vs `Nexora_Demand_Generation_Rules.md`) in a docs-only change when someone asks.

The next implementation step, after those answers, is **Phase 0 only**: a fixture that runs the legacy CASE and `evaluate` on the same inputs and prints both quantities. No UI, no migration, no quantity change in either live path.
