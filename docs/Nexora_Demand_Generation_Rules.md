# NEXORA Demand / Order Generation Rules (one page)

Reflects the **live production engine** after the 2026-09-26 legacy-parity fix
(2026-08-23 stock-netting fix + three VB.NET parity additions below).
Source of truth: `backend/modules/procurement/decision_rules.py` (rules) +
`decision_repository.py` (inputs). Rules are pure Python; SQL only reads inputs.

**Design intent: NEXORA = VB.NET (legacy) + improved.** Every legacy floor/gate
is now present as an OR-added superset term (never removed or shrunk); the
new audit-trail (`reason_code`, `trigger_reason`, `movement_class`,
`stock_status`) has no legacy equivalent and stays additive on top.

## Inputs (per product, per store — from `NEXORA_PLATFORM.sync.*`)
| Input | Source |
|---|---|
| `window_sales_qty` | SUM of **valid retail** sales (`SeriesTransID=1`, `TransactionValidity=0`, `DontConsiderInOrder=0`) within the rolling window (`today − RollingDays`) |
| `max_day_sale_qty` | MAX of per-**day** sale sums in window |
| `max_bill_qty` | MAX of per-**bill** sale sums in window |
| `billing_frequency` | distinct bills in window |
| `current_stock` | latest-month `sync.ProductTrans.StockInHand` (fallback `Products.TotalStock`, then 0) |
| `sale_unit` | `Products.SaleUnit` (strip/pack size) |
| `last_sale_date` | **MAX real** `ProductSaleInformation.TransactionDate` (valid retail, full history) |
| `last_received_date` | **MAX real** `PurchaseTrans.grndate` (NULL if never received) |
| pending receivable / in-transit / reserved | **0** (no synced source yet) |

## Parameters
`RollingDays` (default 90), `MinDays`, `MaxDays` (per refresh); `recency_days = 10`.
Classification cutoffs (defaults): movement FAST≥50, MEDIUM≥10; stock LOW<3, SAFE≤15.

## Rule order (terminal skips FIRST, then sizing)
Each exclusion **returns immediately**; only `INCLUDE` products are written to the VPL. No later step can re-add a skipped product. Past/legacy/previous order quantity is **never** an input.

1. **Inactive** product → EXCLUDE.
2. **Do-not-order** flag (`dont_consider`) → EXCLUDE.
3. **Not selling**: `AvgDailySales ≤ 0` (no eligible sales in window) → EXCLUDE `NOT_SELLING`.
4. **HARD SKIP — no sale in last 10 days**: `last_sale_date` is null or `< today − 10d` → EXCLUDE `STALE_SALE`.
5. **HARD SKIP — no sale after latest GRN**: a GRN exists **and** `last_sale_date < last_received_date` → EXCLUDE `RECENTLY_RECEIVED`. (Same-day `sale == GRN` is **kept** — legacy-faithful `>=`. No GRN ⇒ rule N/A.)
6. **Adequate cover** (qualification gate, legacy-parity ADDED 2026-09-26):
   product qualifies (is NOT excluded) if **either** `DaysCover < MinDays`
   **or** `EffectiveAvailable < MinQtyFloor`, where
   `MinQtyFloor = MAX(CEIL(AvgDailySales × MinDays), CEIL(WindowSalesQty / BillingFrequency))`
   — legacy's exact `minqty` formula (`order_local/remote.sql`), floors a
   lumpy/slow mover by its **average quantity per bill**, not just its day
   average. Only excluded (`ADEQUATE_COVER`) when **both** conditions fail.
   6a. **Rare-mover top-up** (legacy "Additional Row" parity): if neither
   condition above qualifies the product, but `EffectiveAvailable ≤ 1` **and**
   `MinQtyFloor ≤ 1` **and** `BillingFrequency > 1` **and**
   `WindowSalesQty > 1` → INCLUDE a forced 1-strip top-up
   (`INCLUDED_RARE_MOVER_TOPUP`) instead of excluding — legacy force-orders
   qty=1 for near-out-of-stock, infrequently-sold items that fail every other
   gate.

**Sizing (qualified products only):**
7. `AvgDailySales = window_sales_qty / RollingDays`
8. `EffectiveAvailable = current_stock + pending_receivable + in_transit − reserved` (currently = `current_stock`)
9. `DaysCover = EffectiveAvailable / AvgDailySales`
10. `TargetStock = AvgDailySales × MaxDays`
11. **`GrossTarget = MAX(TargetStock, MaxDaySaleQty, MaxBillQty, MaxLineSaleQty)`** — spike floors are required **stock levels**, not add-ons. `MaxLineSaleQty` (legacy-parity ADDED 2026-09-26) is legacy's exact spike metric (`MaxSalesQtyInBill` = MAX single sale-**line** quantity); NEXORA's day-sum/bill-sum floors are additional, stronger terms legacy never had — this restores legacy's own floor as a superset term so NEXORA orders at least what legacy's spike protection would.
12. **`Required = GrossTarget − EffectiveAvailable`** — stock subtracted **exactly once** (legacy parity: `ceil((maxqty − stock)/pack)`).
13. `FinalQty(loose) = CEILING(Required)`
14. `SuggestedQty(packs) = CEILING(FinalQty / SaleUnit)`
15. `Determinant = COVERAGE | SPIKE_PROTECTION | MAX_BILL_TRIGGER | RARE_MOVER_TOPUP` (which term set `GrossTarget`, or the rare-mover top-up path).
16. `FinalQty ≤ 0` → EXCLUDE `ZERO_REQUIRED` (cannot occur once qualified).

## Points not yet in the application (gaps)
- Pending receivable / in-transit / reserved are always **0** — open POs/GRNs and reservations do not reduce demand (no synced source yet).
- Stock source is `ProductTrans.StockInHand` (NEXORA choice, owner-ruled 2026-07-15 — see [[procurement-store-stock-source]]), which differs from legacy `Products.TotalStock` for some products. **Not reverted to legacy** — TotalStock was found stale/wrong for ~26% of a real store's catalogue; reverting would reintroduce that bug. Flagged for explicit owner sign-off if legacy-exact parity on this field is truly wanted.
- No supplier assignment at generation (separate stage); no supplier MOQ / pack-multiple beyond single-pack rounding.
- No expiry / near-expiry suppression, no seasonality/trend weighting, no lead-time reorder point / safety stock.
- Classification cutoffs and `recency_days` are fixed defaults (not per-store configurable / not surfaced in the refresh UI).

**Closed 2026-09-26 (were gaps, now legacy-parity ADDED, not swapped in):**
- ~~Qualification uses days-cover only~~ → per-bill `MinQtyFloor` OR-added (rule 6).
- ~~Spike metric differs from legacy (day/bill vs line)~~ → `MaxLineSaleQty` OR-added as a third floor term (rule 11).
- ~~No "Additional Row" equivalent~~ → `RARE_MOVER_TOPUP` path added (rule 6a).

---
## Future suggestions (for your review — not yet implemented)
1. Wire **pending receivable** (open GRN/PO) and **reserved** into `EffectiveAvailable` — no synced source exists yet, needs a new sync table before this can be real (not fakeable from current data).
2. Decide whether legacy's `Products.TotalStock` should override `ProductTrans.StockInHand` for order-generation specifically — currently NOT changed (see gap above); this is a data-source ruling, not a formula gap.
3. Make **recency window, Min/Max days, classification cutoffs** per-store configurable.
4. **Lead-time-aware reorder point** with safety stock instead of flat MinDays.
5. **Expiry-aware** suppression (skip reorder of soon-to-expire lines).
6. **Seasonality / trend** weighting rather than a flat rolling average.
7. Configurable **same-day GRN** handling (treat `sale == GRN` as moved vs not).
8. **Supplier MOQ / pack-multiple** rounding at sizing time.
9. Align spike metric with legacy (single-line max) if exact legacy parity is desired.
