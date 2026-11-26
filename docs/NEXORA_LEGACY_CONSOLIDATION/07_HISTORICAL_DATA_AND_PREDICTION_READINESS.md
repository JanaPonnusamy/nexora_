# Historical Data & Prediction Readiness

Status tags: **VERIFIED** (read the actual code/SQL cited), **PARTIAL** (read some, inferred the
rest), **INFERRED** (reasoned from adjacent code, not directly read), **UNKNOWN** (not found).

## 0. Headline findings

1. **No machine learning exists anywhere in this codebase.** `product_category_ai.py` is the only
   file with "ai" in its name among the modules investigated; it is a **rule-based-fallback, LLM-
   assisted shelf-category classifier** — a single `anthropic.Anthropic().messages.create(...)` call
   per batch of product names, with structured JSON output, used ONLY to suggest a shelf-sort
   category (Tablet/Syrup/Food/etc.) for display-layer grouping (`product_category_ai.py:1-31,79-95`).
   It is not involved in demand, quantity, stock, or any forecasting decision; it degrades to
   keyword/cross-store rules with zero functional loss when no API key is configured
   (`product_category_ai.py:9-14,29-31`). **No `sklearn`, `torch`, `numpy`-based model, trained
   weights file, or scoring function was found in any of the files read for this audit.** VERIFIED.
2. **No demand-forecasting, seasonal-index, or trend-extrapolation logic exists on either the Legacy
   or NEXORA side.** Both engines compute a quantity from a rolling historical window (90 days on the
   legacy/live-default path; configurable `rolling_days` on the rollback engine) — this is a **moving-
   sum/moving-average**, not a forecast. VERIFIED (absence confirmed by reading all 12 named
   procurement rule files plus `legacy_order/order_process.py`, `rulebook_order.py`).
3. **The central/platform copy of transactional history (`sync.ProductSaleInformation`,
   `sync.PurchaseTrans`, `sync.ProductTrans`) is NOT retention-purged** — the only retention/purge
   logic found anywhere in the codebase lives in `backend/modules/ordernmc_mirror/service.py` and
   applies **only to the REMOTE mirror copy** pushed down to a store's own SQL Express instance (10 GB
   cap), not to the HO-side `OrderNMC`/`NEXORA_PLATFORM.sync.*` data the order and procurement engines
   actually read from. VERIFIED — see §2 below.

---

## 1. Dataset-by-dataset inventory

### 1.1 Historical sales by product/store/date

- **Source table**: `sync.ProductSaleInformation` (platform copy of the branch `ProductSaleInformation`
  table). VERIFIED via `decision_repository.load_source`'s `sales`/`leg_sales` CTEs
  (`decision_repository.py:96-109,154-168`) and `order_local.sql`'s `SalesQuantity` CTE.
- **Granularity**: one row per sale LINE, with a real `TransactionDate` (date+time), `Quantity`,
  `SeriesTransID`, `TransactionValidity`, `DontConsiderInOrder`, bill number (`Bnumber`/`BillNumber`),
  series name. This is genuine line-level transactional history, not a monthly rollup. VERIFIED —
  confirmed by every window/aggregation query reading it (`order_local.sql:1`; `decision_repository.py:96-198`;
  `order_rulebook_inputs.sql:12-21`).
- **Sync mechanism**: incremental sync keyed by `PS.ID > ?` with **no date filter at all**
  (`sync_engine.get_query_for_table`, `sync_engine.py:62-70`) — every new row the branch DB produces is
  pulled forward; nothing is dropped during normal incremental sync. VERIFIED.
- **Earliest/latest date**: cannot be determined from code alone (depends on how long each store's own
  branch SQL Server has existed and how far back its own history reaches) — the sync layer itself places
  no floor. The *order engines* only ever read a 90-day (legacy/live-default) or configurable
  `rolling_days` window of it for quantity calculation, but the **underlying stored history is not
  limited to that window** — it is read in full by anything that queries it directly (e.g. the abnormal-
  sales 90-day lookback independently re-reads the same table, `abnormal_sales.py:30`,
  `abnormal_sales_service.py:46-47`). PARTIAL (mechanism verified; actual earliest date is a live-DB fact
  this read-only code audit cannot determine).
- **Retention on the HO/platform side**: **none found**. VERIFIED by absence (no DATEADD/purge logic in
  `backend/modules/sync/*.py` touching `ProductSaleInformation`; the only DATEADD-based retention found
  anywhere, `ordernmc_mirror/service.py:54-60`, explicitly targets "the remote OrderNMC" (10 GB SQL
  Express cap at a *store*, pushed FROM the HO), not the HO's own copy).
- **Retention on the remote-mirror side** (if a store receives a mirrored copy): 365 days by
  `TransactionDate`, via `ORDERNMC_MIRROR_PSI_KEEP_DAYS` (default 365) — `ordernmc_mirror/service.py:51-60`.
  VERIFIED. This matters only for a store that is a *mirror target*, not for HO's own data.
- **Store/product coverage**: every store that syncs to the platform; every product with at least one
  sale line. No sampling/filtering beyond `TransactionValidity`.
- **Data quality note**: `TransactionValidity` interpretation beyond "0 = valid" is explicitly UNVERIFIED
  in the rules registry itself (`PRR-SAFE-TXNVALIDITY`, `rules_catalog.py:413-427`: "Cancelled versus
  modified is not mapped... Remain blocked"). Any historical analysis treating non-zero validity codes
  as a meaningful category (e.g. distinguishing a cancelled bill from an edited one) would be guessing.
- **Prediction suitability**: **YES — this is the strongest dataset in the system for prediction.** Real
  line-level, dated, multi-year-capable transactional history exists; it is read repeatedly for rolling-
  window aggregation today but nothing currently builds a longer time series (weekly/monthly buckets,
  year-over-year comparison) from it. VERIFIED usable; UNKNOWN exact depth without a live DB query.

### 1.2 Historical purchases and purchase prices

- **Source table**: `sync.PurchaseTrans` (platform copy). VERIFIED via `supplier_repository.top_suppliers`
  (`supplier_repository.py:40-69`), `decision_repository.load_source`'s `grn` CTE (`decision_repository.py:145-150`),
  and the legacy `qty_check_purchase_details`/margin functions (`legacy_order/repository.py:1687-1761,2152-2170`).
- **Granularity**: one row per GRN line, with `GRNDate`, `GRNNumber`, `SupplierCode`, `PurchasePrice`,
  `ItemCost`, `MRP`, `StockReceived`, `FreeQty`, `ProductDiscPercent`/`DiscountAmount`, `BatchCode`,
  `InvoiceSeries` (used to exclude internal transfers, `'TI'`, from offer detection — `repository.py:344-348`).
  Real dated transactional history, not a snapshot. VERIFIED.
- **Retention**: same situation as §1.1 — unbounded on the HO/platform side; 365 days by `grndate` on a
  remote mirror target only (`ORDERNMC_MIRROR_TRANS_KEEP_DAYS`, `ordernmc_mirror/service.py:57`). VERIFIED.
- **Coverage/quality**: `SupplierCode` is present per the ranking queries' `WHERE pt.SupplierCode IS NOT NULL`
  filter (`supplier_repository.py:61`), implying some rows legitimately have no supplier code (internal
  transfers, direct stock adjustments) and are excluded from supplier-ranking reads but still present in
  the table. `PRR-SUP-TAX-BASIS` (`rules_catalog.py:293-307`) flags that whether `PurchasePrice`/`ItemCost`
  is tax-inclusive is UNVERIFIED — a real data-quality caveat for any cost-trend analysis.
- **Prediction suitability**: **YES for purchase-rate trend analysis** — enough dated, per-supplier,
  per-product granularity exists to build a real price-over-time series. Currently only ever read as
  "last N GRNs" (`PRR-SUP-COST` target: latest 6 records, `rules_catalog.py:286-291`) or "most recent GRN
  date" (`supplier_repository.py:68`) — never as a trend/time series.

### 1.3 Historical stock levels

- **Two very different stock representations exist, and conflating them is the #1 risk flagged in the
  companion business-rule-comparison doc (rule #7):**
  - **`sync.Products.TotalStock`** — a single current value per product, overwritten on every sync. This
    is a **snapshot, not a history**. VERIFIED (`order_local.sql:1`; `decision_repository.py:216`).
  - **`sync.ProductTrans.StockInHand`**, keyed by `(store_id, ProductCode, MonthOfStatistics)` — a
    genuine **monthly time series** of stock-on-hand per product per store. VERIFIED: `_dbutil.store_stock_expr`
    reads this via `ORDER BY MonthOfStatistics DESC` to get the latest month
    (`_dbutil.py:22-35`), which only makes sense if multiple `MonthOfStatistics` rows exist per product —
    i.e. the table itself IS the historical series, even though every current consumer only ever reads
    its latest row.
- **Retention**: `ProductTrans` has the same 365-day (`ORDERNMC_MIRROR_TRANS_KEEP_DAYS`) remote-mirror
  clip as §1.1/§1.2 (`ordernmc_mirror/service.py:58`), unbounded on the HO/platform side. VERIFIED.
- **Granularity caveat**: month-level, not day-level. A day-by-day stock curve cannot be reconstructed
  from `ProductTrans` alone; only a month-over-month stock trend can.
- **Prediction suitability**: **PARTIALLY YES** — `ProductTrans.StockInHand` is a real multi-month time
  series (not just a snapshot), suitable for month-over-month stock trend/stockout-risk analysis, but
  nothing in the code currently reads more than the single latest month. `Products.TotalStock` alone
  (the other common stock source) has **zero historical value** — it is overwritten in place.

### 1.4 Historical supplier stock

- **Contradicts the prior memory hint** ("Supplier Live Stock... supplier stock historical tracking
  exists") — on closer reading, **both the legacy and NEXORA supplier-stock tables are current-snapshot-
  only, not time series:**
  - Legacy `SupplierStock` (central OrderNMC): `repository.replace_supplier_stock` does
    `DELETE FROM SupplierStock WHERE storename=? AND suppliercode=?` immediately followed by a bulk
    `INSERT` (`legacy_order/repository.py:918-934`) — every refresh **destroys** the prior snapshot before
    writing the new one. VERIFIED. There is no `SupplierStockHistory` table referenced anywhere in the
    files read.
  - NEXORA `procurement.supplier_stock`: same pattern — `supplier_stock_repository.get_supplier_stock`
    reads it as a plain current table with one `transaction_date` column (last-import timestamp), joined
    live against the current VPL (`supplier_stock_repository.py:42-81`); no historical table name
    (`supplier_stock_history`, `vpl_history` is unrelated) appears anywhere in `supplier_stock_repository.py`,
    `supplier_stock_service.py`, or `supplier_stock_import.py` (names checked, contents of the latter two
    not fully read but the repository — the only read path — confirms snapshot shape).
- **Correction to the prior memory note**: the "Supplier Stock TotalStock mismatch fix" memory's root
  cause (a stalled `ProductTrans` sync) was about *store* stock, not supplier stock history — it does not
  imply supplier-stock time-series tracking exists. That earlier memory conclusion should be treated as
  about sync *freshness*, not data *depth*.
- **Prediction suitability**: **NO** — there is no historical supplier-stock series to analyze trend from.
  Each import overwrites the last. If "supplier availability trend" prediction is wanted, a new
  append-only history table would need to be added (see Missing Data, below) — this is a genuine gap,
  not a misconfiguration of something that already exists.

### 1.5 Historical schemes/free quantities

- **Source**: `sync.PurchaseTrans.FreeQty` per GRN line (same table as §1.2) — real dated history of when
  a free-quantity scheme was received. VERIFIED (`repository.py:1746-1761`; `supplier_stock_repository.products_with_offers`).
- Also `procurement.supplier_stock.scheme`/`free` columns on imported current supplier price lists — these
  are **current-offer snapshot fields**, not historical (overwritten per import, same as §1.4).
- **Prediction suitability**: **PARTIALLY YES for the GRN-side data** (real dated scheme-received history
  exists in `PurchaseTrans`, currently only consumed as a boolean "has ever had free qty," never as a
  frequency/seasonality signal). **NO for the current-offer side** (snapshot only).

### 1.6 Product launches/discontinuations

- UNKNOWN / not directly trackable from anything read. `sync.Products.isActive` + `CreationDate` exist on
  the Products table per the sync query (`sync_engine.py:54-61`: `CreationDate, ModifiedDate, isActive`
  columns are synced), which COULD support a "when did this product first appear / go inactive" read, but
  no code in the 12 procurement files or the legacy order files reads `CreationDate` or tracks an
  isActive transition over time — only the current `isActive=1` value is filtered on everywhere
  (`order_local.sql:1`; `decision_repository.py:231-233`). INFERRED: the raw data to determine a launch
  date exists (`CreationDate`), but discontinuation (isActive flipping to 0) is a transition that is only
  ever read as a current state, never logged with a "when did it change" timestamp — so a true
  discontinuation DATE cannot be reconstructed, only "is currently inactive."

### 1.7 Stockout periods, expiry/wastage

- **Stockout periods**: UNKNOWN — no "stock reached zero on date X, recovered on date Y" tracking found.
  `ProductTrans.StockInHand` (§1.3) COULD show a month where stock was 0, but month-granularity cannot
  identify a stockout's actual duration within that month.
- **Expiry/wastage**: `backend/modules/expiry_report` and `expiry_stock` read `sync.SupplierAckHeader`/
  `SupplierAckDetail`/`SupplierAdj*` settlement tables (Shopaid supplier-expiry sync) — these ARE real,
  dated, event-based records (an ack transaction, a settlement, with quantities), not a snapshot
  (`expiry_report/repository.py:1-30`: "Given/Received/Pending are three independent measures over their
  own date semantics"). VERIFIED as genuine historical event data, validated to the penny against the
  legacy stored procedures per the module's own docstring.
  `backend/modules/nonmoving_report` reads `sync.Batches` for **current** dwell-days (days since
  `LastSaleDate`/`LastReceivedDate` computed at query time from the batch's own two date columns) — this
  is a current-state calculation over two point-in-time fields on a current snapshot row, not a dwell-
  history time series (`nonmoving_report/repository.py:1-20`). No wastage/write-off quantity tracking was
  found in either module (Given/Received/Pending in `expiry_report` concerns supplier-ack settlement
  flow, not write-off due to physical expiry).
- **Prediction suitability**: Expiry-ack data (§ above) — YES, genuine dated event history exists and is
  already validated against legacy SPs; could support expiry-risk trend analysis per supplier. Stockout-
  duration and wastage — NO, not trackable from anything found.

### 1.8 Actual order quantities vs actual received quantities

- **Source**: `procurement.procurement_order_items` (final/suggested qty) joined against GRN data via
  `reconciliation_rules.match_receipts`/`assignment_state`/`item_receipt_state`
  (`reconciliation_rules.py:1-74`) — matches a supplier assignment to `PurchaseTrans` receipts by product
  (+ supplier when available). VERIFIED as a real, computed reconciliation (not a snapshot) — it derives
  `remaining = assigned - received` live from the order item plus the synced purchase data.
- **Historical depth**: each Refresh's order items are a point-in-time record (tied to one `refresh_id`);
  whether a full history of every past Refresh's final-vs-received comparison survives depends entirely
  on whether old `procurement_order_items`/`procurement_virtual_products` rows are ever deleted. VERIFIED
  that `decision_repository.clear_products` **deletes** the prior VPL for a `refresh_id` on regeneration
  (`decision_repository.py:276-286`) — but this clears a FUTURE regeneration of the SAME refresh_id, not
  past, already-finalized refreshes; a new Refresh gets a new `refresh_id` and old refreshes' rows are
  not shown as being cleaned up anywhere in the files read. PARTIAL — old Refreshes likely persist as
  rows (no delete-all-old-refreshes job found), but this was not independently confirmed by reading a
  scheduled-purge job for `procurement_virtual_products`/`procurement_order_items` by age.
- **Prediction suitability**: YES, if old Refresh rows are in fact retained (plausible given no purge job
  was found) — this is exactly the data needed to **backtest** any new forecasting approach (compare what
  was ordered/suggested against what was later actually received and actually sold).

### 1.9 Order adjustments, actual post-order sales

- **Order adjustments**: legacy audit trail via `_record_line_audit` (`repository.py:2112-2115`, called
  from manual-adjust/skip paths) — a genuine per-line change log (old qty → new qty, actor, timestamp).
  VERIFIED as real historical event data.
- **Post-order sales**: `ProductSaleInformation` (§1.1) continues accumulating after an order is placed —
  nothing prevents correlating "ordered on date X" against "sales in the N days after X" using the same
  table already described. No code currently does this correlation.
- **Prediction suitability**: YES for both — real dated records exist for order adjustments and for
  post-order sales; neither is currently used as a backtest signal.

---

## 2. Retention summary (the "12mo/90d" memory hint, verified)

`backend/modules/ordernmc_mirror/service.py:51-60` — **VERIFIED, exact text**:

```
# Remote retention (owner, 2026-11-06): the remote OrderNMC is SQL Express (10 GB
# cap), so transaction history older than 12 months is not sent and the agent purges rows past the window.
# OrderManagementBackup keeps 90 days for the remote user's order compare.
RETENTION = {
    "ProductSaleInformation": ("TransactionDate", 365),
    "SaleInformation":        ("BillDate", 365),
    "PurchaseTrans":          ("grndate", 365),
    "ProductTrans":           ("MonthOfStatistics", 365),
    "OrderManagementBackup":  ("Transactiondate", 90),
}
```

**This retention applies ONLY to data the HO pushes down to a remote store's own SQL Express copy** (the
"OrderNMC mirror" feature, used so a remote/agent-connected store has a locally-queryable copy without
exceeding its 10 GB Express cap). **It does NOT purge or limit the HO's own central `OrderNMC`/
`NEXORA_PLATFORM.sync.*` data** — those are the tables every order-engine and procurement query in this
audit actually reads from. No equivalent purge/retention job was found for the HO-side copies in
`backend/modules/sync/*.py` or `backend/modules/legacy_order/sync_engine.py`. **Practical implication for
forecasting**: the central data's real depth is bounded only by (a) how long each branch SQL Server has
existed and (b) how long ago NEXORA started syncing from it — not by any retention policy in this
codebase. Determining the actual earliest date requires a live database query, not a code read.

---

## 3. Forecasting readiness assessment

| # | Area | Readiness | Basis |
|---|------|-----------|-------|
| 1 | Demand forecasting | **Data: READY. Logic: NOT BUILT.** `sync.ProductSaleInformation` has real daily/intra-day granularity and (per §2) likely multi-year depth centrally. No forecasting model exists; both engines use a rolling-window moving sum/average only. |
| 2 | Reorder quantity recommendations | **Live today, but not predictive.** Both engines already compute a reorder quantity from historical averages + spike floors (`decision_rules.final_required`, `legacy_order_parity.buyer_result`). This is reactive (what did you sell recently), not predictive (what will you sell). |
| 3 | Seasonal demand | **Data: PARTIALLY READY. Logic: NOT BUILT.** Enough dated sales history likely exists to compute a month-of-year or day-of-week seasonal index, but no code reads more than a 90-day trailing window — nothing aggregates by calendar month/week across years. |
| 4 | Slow-moving detection | **READY AND PARTIALLY BUILT.** `decision_rules.movement_class` already classifies FAST/MEDIUM/SLOW/NONMOVING from avg-daily-sales (`decision_rules.py:107-115`), though the live-default generation profile doesn't currently populate it (see business-rule-comparison doc, rule #18/19). This is a current-state classification, not a trend/prediction. |
| 5 | Non-moving prediction | **Reporting exists, prediction does not.** `nonmoving_report` computes *current* dwell-days from two date columns on a snapshot batch row (§1.7) — this answers "is it non-moving now," not "will it become non-moving." |
| 6 | Supplier availability trends | **NOT READY.** Per §1.4, supplier stock is snapshot-only on both legacy and NEXORA sides — no historical supplier-stock series exists to trend from. This is a genuine data gap, not just an unbuilt feature. |
| 7 | Purchase rate trends | **Data: READY. Logic: NOT BUILT.** `PurchaseTrans` (§1.2) has real dated per-supplier, per-product price history; only ever read as "latest N records," never as a trend. |
| 8 | Stockout risk | **Data: PARTIALLY READY.** `ProductTrans.StockInHand` monthly series (§1.3) could flag months stock hit zero, but month-granularity cannot localize a stockout's actual start/end date or duration within the month. No stockout-specific logic exists. |
| 9 | Excess stock risk | **Data: READY. Logic: PARTIALLY BUILT.** `decision_rules.stock_status` already classifies OUT/LOW/SAFE/OVERSTOCK from current effective-available vs. days-cover (`decision_rules.py:118-126`) — again a current-state classification, usable as an input to a trend model but not itself predictive. |
| 10 | Expiry risk | **Data: READY (ack/settlement side). Logic: NOT BUILT for risk scoring.** `expiry_report`'s ack/settlement data (§1.7) is real dated history validated against legacy SPs; no code computes a forward-looking "this batch/supplier is trending toward more expiry losses" signal — only point-in-time Given/Received/Pending reports. |

---

## 4. Recommended initial deterministic forecasting approach

Given the actual data on hand (confirmed above), a defensible first step — **not machine learning**,
fully explainable, and backtestable against data that already exists — is:

1. **Weekly (not daily) moving average + simple seasonal index**, computed directly from
   `sync.ProductSaleInformation`:
   - Bucket historical sales by `(ProductCode, StoreId, ISO week)` over however much history the central
     copy actually holds (query the live DB to find the true earliest date — not determinable from code
     alone, see §2).
   - Compute a rolling N-week moving average (N=8 or 12 is a reasonable starting point) as the baseline
     demand signal — this is a direct generalization of what `decision_rules.average_daily_sales` already
     does, just at weekly granularity instead of collapsing everything into one 90-day number.
   - If at least 1-2 years of history exist (needs live-DB verification), compute a per-week-of-year
     seasonal index (`week's historical average / overall average`) and multiply the moving average by it
     — this directly answers area #3 (Seasonal demand) without any ML.
2. **Purchase-rate trend**: a simple linear or percentage-change trend over the last 6-12 GRNs per
   (product, supplier) from `PurchaseTrans`, surfaced alongside the existing `PRR-SUP-COST` "latest 6
   records" rule (`rules_catalog.py:286-291`) rather than replacing it — this answers area #7 without new
   infrastructure, since the exact same rows `top_suppliers`/`top_suppliers_bulk` already read would feed
   it.
3. **Stock trend from `ProductTrans.StockInHand`**: instead of only reading the single latest
   `MonthOfStatistics` row (as `_dbutil.store_stock_expr` does today), read the last 3-6 months per
   product/store and compute a simple month-over-month depletion/accumulation rate — this is the cheapest
   possible upgrade to areas #8/#9 (stockout/excess risk) since the underlying monthly series already
   exists and is already keyed correctly for this.

**Backtest plan using data already in the DB** (per §1.8/§1.9, pending live-DB confirmation that old
Refresh rows are retained):
- For each historical Refresh, compare its `suggested_qty`/`final_qty` (what the engine would have/did
  recommend) against the actual sales that occurred in the following cover-days window
  (`ProductSaleInformation`, §1.1) and the actual quantity later received (`PurchaseTrans`, reconciled via
  `reconciliation_rules.match_receipts`, §1.8) — this directly measures over-ordering (excess tied up),
  under-ordering (stockout risk realized), and gives a ready-made ground truth to validate the weekly-
  moving-average + seasonal-index approach above before trusting it over the current 90-day rolling
  calculation.

## 5. What historical data is MISSING for meaningful prediction

1. **Historical supplier-stock series** (§1.4) — both legacy `SupplierStock` and NEXORA
   `procurement.supplier_stock` are destroy-and-replace snapshots. A genuine time series would require a
   new append-only history table (e.g. `procurement.supplier_stock_history`, written alongside — not
   instead of — the current snapshot table on every import) before "supplier availability trend" (area
   #6) can be built at all.
2. **Discontinuation/transition timestamps** (§1.6) — `Products.isActive` is read only as a current flag;
   no event log captures *when* a product was deactivated, so true product-lifecycle analysis (how long
   after launch does a product typically get discontinued, does that correlate with slow-moving
   classification) cannot be reconstructed from what exists today.
3. **Stockout episode boundaries** (§1.7) — `ProductTrans.StockInHand`'s monthly granularity cannot
   localize when stock actually hit zero and when it recovered within a month; a day-level stock ledger
   (even a lightweight derived one, computed from sale/purchase deltas against a known starting balance)
   would be needed for precise stockout-duration analysis.
4. **Wastage/write-off quantities** — no table found anywhere in the modules investigated records a
   physical expiry write-off quantity distinct from the supplier-ack settlement flow in `expiry_report`.
5. **Confirmed-pending-purchase data** — not specific to forecasting alone, but worth repeating here since
   it affects any stockout/excess-risk model: `PRR-STK-PENDING` is explicitly `STATUS_DECISION`/blocked
   because no verified source column for "confirmed supplier pending quantity" exists
   (`rules_catalog.py:150-164`) — any risk model using "effective available stock" inherits this same gap
   until that source is identified.
6. **True earliest-date / depth confirmation** — this audit is code-only per instructions; the actual
   number of years of history sitting in the central `sync.ProductSaleInformation`/`PurchaseTrans`/
   `ProductTrans` tables must be confirmed with a live (read-only) query before committing to a seasonal-
   index design that assumes, say, 2+ years of data are available.
