# 03 — Nexora function catalog

Root: `E:\Nexora\backend\modules\procurement\`. Confidence VERIFIED unless noted.

## Lifecycle

| Function | File | Behavior |
|---|---|---|
| `orchestration_service` refresh | `orchestration_service.py` ~134–241 | Create refresh, `decision_service.generate_vpl`, `order_items_repository.generate_working_items`, `carry_forward_skips`, archive prior refresh. One active cycle per store (same file ~93–105). |
| `decision_service.generate_vpl` | `decision_service.py` ~96–131 | Writes **INCLUDE only**. |
| `generate_working_items` | `order_items_repository.py` ~29–52 | `final_qty = suggested_qty`, `remaining_qty = suggested_qty`, `item_status='draft'`. |
| `workspace_service.skip_item` | `workspace_service.py` 130–139 | Requires non-empty `skip_reason`. |
| `workspace_repository.skip_item` | `workspace_repository.py` 333–346 | Status skipped, final 0, remaining 0. |
| `workspace_repository.set_final_qty` | ~293–311 | Status `review`, `remaining = final − assigned`, sets override fields. |
| `assignment_service` assign | `assignment_service.py` 66–94 | 409 if skipped, duplicate supplier, or other active supplier. Qty must be `> 0` and not exceed `final_qty`. |
| `export_service.export_refresh` | `export_service.py` 22–36 | Batch `EXP-` + uuid. Marks assignments exported. Partial-failure transaction behavior was not re-read line by line this pass: PARTIALLY VERIFIED. |
| `reconciliation_rules.assignment_state` | `reconciliation_rules.py` 18–32 | `remaining = max(0, assigned − received)`. |
| `supplier_service.get_export_settings` / `save_export_settings` | `supplier_service.py` 95–114 | Store+supplier row only. No store-only tier and no system-default row in this repository. |

API surface is `pm_router.py` (workspace, skip, supplier recommendations, export settings). Exact route strings were mapped in the 2026-10-19 audit; they were not re-copied here.

## Quantity engine

`decision_rules.evaluate` (`decision_rules.py` 212–391) and `final_required` (156–205).

```
AvgDailySales = window_sales_qty / rolling_days          # default rolling 90
EffectiveAvailable = max(0, stock + pending + transit − reserved)
MinQtyFloor = MAX(CEIL(avg*min_days), CEIL(window/billing_frequency))
Qualify if DaysCover < min_days OR stock < MinQtyFloor
GrossTarget = MAX(avg*max_days, max_day_sum, max_bill_sum, max_line)
Loose = CEILING(GrossTarget − EffectiveAvailable)
Packs = CEILING(Loose / SaleUnit) if SaleUnit>0 else Loose
```

`load_source` (`decision_repository.py` 147–175):

- Stock: latest-month `ProductTrans.StockInHand` via `_store_stock_expr`, not `Products.TotalStock`.
- `dont_consider` is `CAST(0 AS BIT)` (line 156). Line-level `DontConsiderInOrder=0` is applied in the sales CTE.
- `billing_frequency` is distinct bill key (series|bill|date).
- `max_day_sale_qty` is max of per-day sums. `max_bill_qty` is max of per-bill sums. `max_line_sale_qty` is max row qty.
- Pending fields are not selected. `evaluate` defaults them to 0.
- Recency default `recency_days = 10` (decision_rules.py 70). Last sale is `MAX(TransactionDate)` on valid retail PSI, full history. Last receipt is `MAX(PurchaseTrans.grndate)`.

Excluded products are not stored on the VPL.

## Skip release — defect confirmed

`carry_forward_skips` (`order_items_repository.py` 59–103):

- Carries `until_next_sales` and `until_next_demand`.
- Does not carry `current_refresh`.
- **Both** persistent modes are released when any valid retail sale (`SeriesTransID=1`, `TransactionValidity=0`) has `TransactionDate > reviewed_at`.
- There is no test that the new refresh’s suggested qty is positive.
- A sale of any size releases `until_next_demand`. That contradicts the agreed rule (release only when a fresh calculation shows positive demand; a sale alone must not release post-purchase suppression, and refresh alone must not release until-next-demand).

`DontConsiderInOrder` is not in the skip-release EXISTS. A dont-consider sale can release a skip. VERIFIED gap.

## Ranking

`purchaseValue.ts` `AA_WEIGHTS`: mapping 100, last purchase 40, frequency 30, PTR 20, live stock 10. `marginPercent` and `costMarginPercent` are display-only (comments at 92–113). No effective-unit-cost formula `(qty×PTR×(1−discount))/(qty+free)` exists in this file. UNKNOWN in SQL purchase history until a query is cited; none was found in `supplier_service.py` get_queue signature review (returns `last_purchase_rate` only).

## Authorization

Nexora login is `backend/controllers/auth_controller.py`. Full access roles include platform admin names. It is not the VB `Users.Role` integer. Store scoping for legacy order is separate (`backend/tests/test_legacy_order_store_access.py`). A PM-vs-Admin split matching VB Role 1/2 was not found inside `decision_rules` or `orchestration_service`. PARTIALLY VERIFIED: procurement routes assume an authenticated tenant user; the VB menu split is not replicated there.
