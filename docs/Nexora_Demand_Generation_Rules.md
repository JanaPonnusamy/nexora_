# NEXORA Demand / Order Generation Rules (one page)

Reflects the **live production engine** after the 2026-08-23 fix.
Source of truth: `backend/modules/procurement/decision_rules.py` (rules) +
`decision_repository.py` (inputs). Rules are pure Python; SQL only reads inputs.

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
6. **Adequate cover** (qualification gate): `DaysCover ≥ MinDays` → EXCLUDE `ADEQUATE_COVER`.

**Sizing (qualified products only):**
7. `AvgDailySales = window_sales_qty / RollingDays`
8. `EffectiveAvailable = current_stock + pending_receivable + in_transit − reserved` (currently = `current_stock`)
9. `DaysCover = EffectiveAvailable / AvgDailySales`
10. `TargetStock = AvgDailySales × MaxDays`
11. **`GrossTarget = MAX(TargetStock, MaxDaySaleQty, MaxBillQty)`** — spike floors are required **stock levels**, not add-ons.
12. **`Required = GrossTarget − EffectiveAvailable`** — stock subtracted **exactly once** (legacy parity: `ceil((maxqty − stock)/pack)`).
13. `FinalQty(loose) = CEILING(Required)`
14. `SuggestedQty(packs) = CEILING(FinalQty / SaleUnit)`
15. `Determinant = COVERAGE | SPIKE_PROTECTION | MAX_BILL_TRIGGER` (which term set `GrossTarget`).
16. `FinalQty ≤ 0` → EXCLUDE `ZERO_REQUIRED` (cannot occur once qualified).

## Points not yet in the application (gaps)
- Pending receivable / in-transit / reserved are always **0** — open POs/GRNs and reservations do not reduce demand.
- Qualification uses days-cover only; legacy also floors `MinQty` by **average-qty-per-bill** (`ceil(slsqty/Frequence)`) — not applied here.
- Spike metric differs from legacy: NEXORA = max single-**day** & single-**bill** sums; legacy = max single-**line** (`MaxSalesQtyInBill`).
- Stock source is `ProductTrans.StockInHand` (NEXORA choice), which differs from legacy `Products.TotalStock` for some products.
- No supplier assignment at generation (separate stage); no supplier MOQ / pack-multiple beyond single-pack rounding.
- No expiry / near-expiry suppression, no seasonality/trend weighting, no lead-time reorder point / safety stock.
- Classification cutoffs and `recency_days` are fixed defaults (not per-store configurable / not surfaced in the refresh UI).

---
## Future suggestions (for your review — not yet implemented)
1. Wire **pending receivable** (open GRN/PO) and **reserved** into `EffectiveAvailable`.
2. Optional **average-per-bill floor** on qualification for lumpy/slow movers (full legacy parity).
3. Make **recency window, Min/Max days, classification cutoffs** per-store configurable.
4. **Lead-time-aware reorder point** with safety stock instead of flat MinDays.
5. **Expiry-aware** suppression (skip reorder of soon-to-expire lines).
6. **Seasonality / trend** weighting rather than a flat rolling average.
7. Configurable **same-day GRN** handling (treat `sale == GRN` as moved vs not).
8. **Supplier MOQ / pack-multiple** rounding at sizing time.
9. Align spike metric with legacy (single-line max) if exact legacy parity is desired.
