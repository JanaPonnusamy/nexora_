# 06 — Procurement rulebook

Two layers. **Current** is what the code does. **Agreed target** is the rule in the unification prompt. Where they differ, the target is not implemented.

## Agreed target (locked by the prompt)

Parameters: 90 calendar days, recency 15 days, min cover 13, max cover 18, stock = `Products.TotalStock`.

Eligibility, before any target math:

- Drop cancelled lines. The code proxy today is `transactionvalidity = 0`. Whether every cancelled bill uses a non-zero validity is UNKNOWN.
- Drop `DontConsiderInOrder <> 0`.
- Do not double-count a modified bill. No implementation found. UNKNOWN until a revision column is identified.
- Sum valid lines of the same product on the same bill before bill metrics.
- Max day = sum of valid qty for that product on one calendar date.
- Average bill = total valid qty / count of distinct bills.
- Average daily = valid qty / 90, including zero days. Both engines already divide by the window length (hard-coded 90 in VB).
- No valid sale in 15 days: off the normal list, visible on a separate PM list.
- Post-purchase: suppress when last valid sale is strictly before the latest actual receipt. A later small sale does not release the line unless min-days eligibility passes.
- `SaleUnit` null, 0, or non-positive: data error, no automatic qty. Do not substitute 1.

Quantity, only after eligibility:

```
gross = MAX(avgDaily*18, maxBillQty, maxDayQty, avgBillQty)
net   = gross - TotalStock - confirmedSupplierPending
packs = CEILING(net / SaleUnit) when net > 0 and SaleUnit is valid
```

Confirmed supplier pending = confirmed order qty minus received qty, after cancelled order qty and valid reversals. Drafts, failed exports, and unexported assignments are not pending.

Skips:

| Mode | Release |
|---|---|
| This order only | Next fresh order may recalculate. Not carried. |
| Until next sales | After a new valid sale, then normal eligibility. |
| Until next demand | When a fresh calculation has positive demand. Refresh with zero demand does not release. |
| Zero qty | Not a skip. Needs no skip reason. |

Roles (agreed names; VB only stores integers): Admin starts and closes orders and configures templates. PM reviews, assigns, marks pending or not supplied, exports, uses the portal, and submits to Admin. One active order per store. Ignored unassigned lines do not block close. Close is allowed with outstanding deliveries after a summary of unfinished assigned work.

Supplier modes stay separate. Manual assignment wins. Auto Assign Remaining fills only empty lines. Assignment does not change buyer-confirmed qty.

Effective cost: last 90 days of received purchases, per supplier and branch, latest six if more exist. Each record is `(paid units x price x (1 - discount)) / (paid units + free)`. A current offer is not applied to an older record. No record in 90 days: `Stale Price — Manual Review`, out of auto rank.

Example target, not found in code: PTR 100, 10% discount, 10+2 offer → `(10 x 100 x 0.90) / 12 = 75`.

Cross-branch fuzzy match is display plus explicit confirm. Never auto-assign. No sales in any branch for 180 days: warning in the existing suggestion box.

Portal: backend worker, Playwright adapter, Selenium left as fallback until the adapter is proven. Unknown availability blocks portal submit. Portal stock does not change final qty.

## Current formulas (not the target)

### VB local (`FetchSourceData`, Form1.vb 5997)

```
min = MAX(CEIL((slsqty/90)*minDays), CEIL(slsqty/COUNT(DISTINCT line ID)))
max = MAX(CEIL((slsqty/90)*maxDays), MAX(line qty))
packs = CEILING((max - TotalStock) / SaleUnit)   if SaleUnit > 0 else 0
gate  = sale within 10 days AND min > TotalStock AND (max-stock)/SaleUnit > 0
        AND lastSale >= lastReceipt
```

Additional-row candidates are stored at qty 0, status 2.

### Nexora (`decision_rules.final_required`)

```
gross = MAX(avg*maxDays, maxDaySum, maxBillSum, maxLine)
packs = CEILING(CEILING(gross - StockInHand) / SaleUnit)  or loose units if SaleUnit <= 0
gate  = sale within 10 days AND (cover < minDays OR stock < minFloor)
        AND not (lastSale < lastReceipt)
```

A rare mover that fails the gate but matches the additional-row predicate is included at 1 pack.

## Worked difference

Window qty 180, 4 distinct bills, max line 20, max bill 60, max day 80, avg bill 45, TotalStock 30, SaleUnit 10, min 13, max 18, pending 0. Recency passes.

| Engine | Gross | Packs |
|---|---|---|
| VB | MAX(36, 20) = 36 | CEILING(6/10) = 1 |
| Nexora | MAX(36, 80, 60, 20) = 80 | 5 |
| Agreed target | MAX(36, 60, 80, 45) = 80 | 5 |

Nexora matches this example only while max day wins, pending is 0, and the stock columns match. Pending of 20 makes the target `CEILING(30/10) = 3` and leaves Nexora at 5.

Second example: max day 20, max bill 20, max line 20, avg bill 45, avg times 18 = 36, stock 30, pack 10.

| Engine | Packs |
|---|---|
| VB | 1 (gross 36) |
| Nexora | 1 (gross 36) |
| Target | 2 (gross 45) |

The average-bill term is the piece neither engine puts in the gross target. VB uses that average only inside `minqty` for eligibility, and it divides by line id, not by bill.

## SaleUnit

| Case | VB local | Nexora | Target |
|---|---|---|---|
| SaleUnit 10, net 14 | CEILING(14/10) = 2 | CEILING(14/10) = 2 | 2 |
| SaleUnit 0 | Order qty 0 | Loose units | Block, no auto qty |
| SaleUnit missing | Same as 0 | Loose units | Block |
