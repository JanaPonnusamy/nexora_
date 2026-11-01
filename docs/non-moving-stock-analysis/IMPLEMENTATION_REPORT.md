# Non-Moving Stock Analysis — Implementation Report

Date: 2026-11-01 · Scope: Phases 0–5 of the "Non-Moving Stock Analysis" master prompt.
Status legend: PASS · PARTIAL · BLOCKED · NOT STARTED.

## 1. Architecture findings (Phase 0)

| Prompt assumption | What the code actually is | Decision |
|---|---|---|
| `Project_Master_Document.md` | Does not exist. Project docs are `PROJECT.md`, `PROJECT_DETAIL.md`, `docs/Procurement_Business_Rules.md`, `docs/procurement-workspace-unification/*`. | Read those instead. |
| "Procurement application / Purchase Manager" with Monthly Trend, All Stores chart, *Other stores — non-moving stock* | These panels live in the **Stock Client** (Electron, `desktop/supplier-stock-client`, React JSX) `ProcurementWorkspace.jsx`, `storeTrends.jsx`, `trendChart.jsx`, `suggestionPanel.jsx`. The web `frontend/` Purchase Manager has none of them. | Module built in the Stock Client, **Purchasing → Non-Moving Stock**. |
| React + TypeScript + Bootstrap 5 + **AG Grid** | Stock Client is React JSX with its own CSS design tokens; **neither app ships AG Grid**. | Used the existing `trp-table` grid conventions (sticky headers, server-side sort/paging, arrow-key navigation). No new grid library. |
| Category filter | `sync.Products.CategoryCode` is blank for every product in every store. | Filter offered on the legacy **Pharma / Non Pharma** split (`ProductType = 0` → Non Pharma, as in `order_local.sql`). |

Reused (not duplicated): `_dbutil.store_stock_expr` (authoritative stock), `intelligence_repository.list_active_stores` / `_floatify`, `dbo.product_mapping` AUTO/APPROVED direct edges (same identity rule as Procurement's Other-stores panel), `legacy_order.service.is_warehouse_store`, `rate_analysis.excel.build_workbook` (Excel), and in the UI `PROCUREMENT_UI.IntelPanel` (Monthly Trend / Purchase-GRN / Sales panels), `StoreTrendsPanel` (All Stores chart), `trendChart.jsx` `TrendBars`/`TrendTip` (grouped bars).

Existing, left untouched: `/api/non-moving-report` (web dwell-days batch report), `/api/reports/non-moving/*` (Stock Client NM bar), Procurement decision engine, VPL, order generation, legacy order workflow.

## 2. Verified data sources (read-only, live NEXORA_PLATFORM, 6 stores)

| Fact | Source | Verification |
|---|---|---|
| Valid sale | `sync.ProductSaleInformation`: `SeriesTransID = 1`, `TransactionValidity = 0`, `Quantity > 0` — the legacy `order_local.sql` rule. Warehouse (NMW) also `SeriesTransID = 11` Transfer-Out (owner ruling 2026-10-07). | Series profile: 1 = C/M/W/X/CR/D sales, 2 = R returns, 11 = TO, 16 = SA/ER/SEA adjustments, 17 = N. Adjustments/expiry returns are **not** sales (the older `store_product_facts` counts them — not reused for that reason). |
| PSI history depth | Starts **2025-04-01** at every store. | "No PSI sale" ≠ "never sold". |
| Last sale fallback | `MAX(ProductTrans.LastBillDate)` (POS rollup, back to 2017), then `MAX(Batches.LastSaleDate)`. | NMA: rollup = PSI date on 12,543 / 12,650 products (99.2%); 406 products only have a pre-2025 rollup date. Source shown on every row; PSI/rollup disagreement flagged. |
| Store stock | `store_stock_expr` = latest `ProductTrans.StockInHand` (owner ruling) | vs sum of batch stock: differs for 255 NMA / 12 NMC / 612 NMG / 14 NMS / 553 NMV / 3 NMW products → shown as `STOCK_MISMATCH`, never valued upward. ProductTrans vs `Products.TotalStock` now agree (0–15 per store). |
| Cost value | `Batches.GrsStkValueatCost` (POS snapshot) | = `Stock × ItemCost ÷ SaleUnit` on 99.8% of batches; the rest have ItemCost 0 where the POS uses PTR. **Raw `Stock × ItemCost` overstates retail stock ~7×** (stock is in loose units, prices per pack). |
| PTR / MRP value | `Stock × PurchasePrice ÷ SaleUnit`, `Stock × MRP ÷ SaleUnit` | Separate measures, never mixed with cost. |
| Expiry | `Batches.ExpiryDate` of in-stock batches; expired < today, near expiry < today + 90 d | 0–9 in-stock batches per store have no expiry date (flagged "No date"). |
| Last purchase / GRN | `PurchaseTrans` — purchase excludes `InvoiceSeries 'TI'` (internal transfer); GRN = any receipt | |
| Cross-store identity | `dbo.product_mapping` AUTO/APPROVED, direct edges both directions | A store mapping to >1 product is flagged ambiguous and never used for transfers. |

## 3. Business rules implemented

**Classification** (configurable `bands`, default 30/60/90/180/365, days since last valid sale):
Active 0–30 · Slow Moving 31–60 · Very Slow 61–90 · Non-Moving Risk 91–180 · Non-Moving 181–365 · Critical Dead Stock > 365.
No sale in any source → **New – No Sale Yet** if first received ≤ 90 days ago (never dead stock), else **No Sales History**.
"Non-moving" (KPIs, Other Stores, transfer sources) = Non-Moving Risk or worse, plus No Sales History.

* Zero (store) stock → not analysed, not valued.
* Last purchase is never used as a last sale.
* Cancelled / invalid sale lines excluded; their 180-day count is shown (`INVALID_SALES`).
* Flags: `STOCK_MISMATCH`, `SALE_DATE_CONFLICT`, `LAST_SALE_FROM_ROLLUP`, `LAST_SALE_FROM_BATCH`, `RECENT_GRN` (≤ 10 days, legacy NM gate), `INVALID_SALES`, `INACTIVE`, `NO_TXN_HISTORY`.

**Transfer recommendations** (recommendations only — nothing is executed):
* Source: in stock, not Active/New, active product; transferable = min(store stock, batch stock) − expired − near-expiry (90 d); a still-selling (Slow / Very Slow) source keeps 90 days of its own sales.
* Destination: directly mapped, same sale unit, unambiguous, active product, sold within 30 days on ≥ 2 bills in 90 days; target = ceil(90-day sales / 90 × 30); need = target − stock.
* Allocation: sources oldest-first, destinations largest-need-first, in whole packs; destination need is tracked so it is never allocated twice.
* Every recommendation carries a reason and the full calculation; every non-moving product without one carries the reason (not mapped / no verified demand / pack differs / ambiguous / no transferable stock / inactive / less than one pack) plus per-store detail.

## 4. Files created

* `backend/modules/nonmoving_analysis/__init__.py`, `repository.py`, `service.py`, `router.py`
* `backend/tests/test_nonmoving_analysis.py` (31 tests)
* `desktop/supplier-stock-client/src/NonMovingStock.jsx`, `nonMovingView.js`, `nonMovingView.test.js` (5 tests)
* `docs/non-moving-stock-analysis/IMPLEMENTATION_REPORT.md`, `PROPOSED_nonmoving_review_tables.sql` (not applied)

## 5. Files modified

* `backend/api/app.py` — import + `include_router` (2 lines).
* `desktop/supplier-stock-client/src/App.jsx` — screen entry `non_moving` (Purchasing), same role gate as Procurement / Rate Analysis, render branch with `ui={PROCUREMENT_UI}`.
* `desktop/supplier-stock-client/src/api/client.js` — `nonMoving()`, `nonMovingExcel()`.
* `desktop/supplier-stock-client/src/styles.css` — appended `nms-*` block (no existing rule changed).

## 6. APIs created (all read-only; prefix `/api/non-moving-analysis`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/stores` | tenant stores + warehouse flag + rule config |
| GET | `/own-store` | Section A grid: filters (search, classes, ptype, supplier, min/max days, expiry, include_zero, non_moving_only), sort, page (≤ 1000), `refresh`, `bands`, `new_days`, `format=xlsx` |
| GET | `/product` | one product: analysed row, batches, every store, transfers / blocks |
| GET | `/product/batches` | batch-wise expiry (store-only, fast) |
| GET | `/other-stores` | Section B (`scope=selling|all`), `format=xlsx` |
| GET | `/transfers` | Section C (`direction=out|in|all`, optional store), `format=xlsx` (+ "No Transfer" sheet) |
| POST | `/transfers/proposal` | Excel proposal of chosen recommendation ids — writes nothing |
| GET | `/dashboard` | Section D + KPIs: by class, store comparison, monthly movement, expiry top 50, `format=xlsx` |
| POST | `/review/export` | Excel of the client-side manual review list — writes nothing |

Authorization: JWT required; tenant-scoped (`assert_tenant_access`); super admin / platform / purchase / admin roles only (salesman → 403), same audience as Rate Analysis; `store_id` must belong to the tenant (404 otherwise).

## 7. Database changes

None applied. No migration was run. `PROPOSED_nonmoving_review_tables.sql` is an **additive proposal** for a shared, audited manual-review list and transfer-proposal register (today the review list and "reviewed ✓/✕" marks live in the PC's localStorage and the proposal is an Excel). Apply only with separate authorization.

## 8. Test results

| Suite | Result |
|---|---|
| `backend/tests/test_nonmoving_analysis.py` | 31 passed — covers acceptance cases 1–14, store isolation, role gate, export-all |
| `backend/tests` (procurement / report / rate / non-moving subset) | 43 passed |
| Root `tests/test_procurement*.py` | 186 passed, **2 failed** (`test_excluded_missing_grn_watermark`, `test_spike_floor_included_binding`) — the same 2 fail on a clean HEAD worktree: pre-existing, not caused by this module |
| Stock Client `node --test src/*.test.js` | 31 passed |
| `vite build` | PASS |
| HTTP (temp backend :8010, startup hooks off) | 401 without token, 404 foreign store, all 9 routes 200, Excel files open (openpyxl) |
| Rendered UI (Playwright, Vite :5197, non-GET blocked) | 1920×1012 light and 1366×768 dark: all four sections, detail tabs, tooltips; no page-level overflow |

Live sanity (all stores, 2026-11-01): NMC 17,887 products in stock, ₹75.21 L at cost (= Σ GrsStkValueatCost), non-moving 4,681 products / ₹13.21 L; NMA non-moving 25.7% of stock value; NMW warehouse 21 non-moving products (expected: it moves stock by transfer-out).

## 9. Performance

* One bulk query per store (temp tables; no per-product / per-store-per-product queries). Warm: ~5 s for NMC (largest), 0.1–1.5 s for every later call from the 30-minute cache.
* Cold tenant-wide build (6 stores, 2 at a time + ~600k mapping edges streamed and filtered): ~100 s. The DB is **SQL Server 2014 Express** (buffer pool capped ~1.4 GB, 4 cores): during a cold build other requests slow down (Procurement's All Stores call timed out at 45 s once; 0.22 s warm). Opening Own Store warms the other stores in the background so the cross-store tabs are usually ready.
* Transfer plan over all stores: ~0.4 s in memory.

## 10. Screenshots

Captured during verification (session scratchpad, not committed — they contain live stock values): Own Store, product detail (Summary / Batches / Other Stores), Other Stores matrix, Transfer Opportunities with expanded calculation, Stock Value & Expiry Risk (light 1920×1012 and dark 1366×768).

## 11. Known limitations

* Valuation/stock are a snapshot (≤ 30 min old, "Data as of" shown; Refresh re-reads).
* Manual review list and transfer "reviewed" marks are per PC (localStorage) until the proposed tables are authorised.
* Monthly Trend / Sales / Purchase panels in the detail reuse the legacy `/api/legacy-order` reads, so they show what Procurement shows (including its window).
* Cold first load is slow on SQL Express (see §9).
* `reports.non_moving_totals` (existing Stock Client NM bar) values stock as raw `Stock × ItemCost`, which overstates retail stores ~7× (see §2). Not changed here (out of scope); flagged for a decision.

## 12. Unresolved business decisions

1. Should a slow but recently-sold product (31–90 days) ever be a transfer source? Implemented: yes, only stock above 90 days of its own sales.
2. Destination cover (30 days), source keep (90 days), near-expiry exclusion (90 days), ≥ 2 bills — defaults, configurable via query params; owner to confirm.
3. Cold-chain / schedule-H / narcotics transfer restrictions — no such product attribute is synced; not enforced.
4. Mapped products whose sale unit differs between stores are blocked rather than converted.
5. Whether the NM bar's `Stock × ItemCost` valuation should be corrected to `÷ SaleUnit` (affects an existing screen).

## 13. Security & authorization

Server-side tenant scope + role gate on every route; store must belong to the tenant; no write endpoints (the two POSTs only build Excel files); no SQL built from user text (all parameters bound; sort keys whitelisted).

## 14. Phase status

| Phase | Status | Note |
|---|---|---|
| 0 Audit & data verification | PASS | |
| 1 Own Store Analysis | PASS | |
| 2 Other Stores Analysis | PASS | |
| 3 Transfer Opportunities | PASS | recommendations + Excel proposal; no execution by design |
| 4 Management dashboard | PASS | |
| 5 Integration & audit | PARTIAL | not yet verified inside the real Electron shell / installed package; frontend not committed (depends on the still-uncommitted Procurement workspace files `storeTrends.jsx`, `trendChart.jsx` and the store-trends API); backend not yet deployed to .80 / HO |
