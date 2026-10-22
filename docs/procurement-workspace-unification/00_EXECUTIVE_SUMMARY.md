# 00 — Executive summary

**Date:** 2026-10-19  
**Status:** Analysis only. No production code, schema, configuration, or live order was changed.  
**Confidence:** Findings below are VERIFIED from source unless marked UNKNOWN.

## What exists

Four separate implementations, not one workspace:

| System | Entry | What it actually does |
|---|---|---|
| VB.NET Order Management | `D:\VBDOTNET\OrderManagement\OrderManagement\Form1.vb` | Login, store pick, process combo, order generation SQL, qty grid, supplier assign, Excel export |
| Nexora Purchase Manager | `backend/modules/procurement/` + `frontend/src/pages/procurement/PurchaseWorkspacePage.tsx` | Cycle/refresh, `decision_rules.evaluate`, review, one-supplier assign, export, GRN reconcile |
| Legacy web + Stock Client | `frontend/src/pages/legacy-order/OrderWorkspacePage.tsx`, `desktop/supplier-stock-client/src/App.jsx` `OrderWorkspace` | UI over `/api/legacy-order`, which runs a Python port of the VB SQL (`order_local.sql`) |
| OrderBot | `D:\VBDOTNET\OrderBot\main.py` | Selenium cart on PharmaRack from `products.csv`. Not wired to Nexora |
| PY | `D:\VBDOTNET\PY` | Purani invoice download and WhatsApp. Not order placement |

Role 1 in VB sees Process Order, Compare Previous Order, mapping, and Access DB. Role 2 does not (`Form1.vb` 288–300). The source never names those integers Admin and PM.

## What the unified Electron workspace requires

A new screen inside Supplier Stock Client, beside the current Order Workspace, with three loaders that must not share one product query:

1. **Qty Check** — lines from the generated order, PM types the supplier (VB `UpdateDatabase(productCode)` assigns on Enter only when the process is not Qty Check).
2. **Auto Purchase Update** — `LoadDataForSupplier`: `OrderManagement` joined to `OrderPurchaseTrans` for the supplier’s past purchases.
3. **Supplier Stock** — `LoadDataForSupplierStock`: `OrderManagement` joined to `SupplierProductMatch` and `SupplierStock` where portal/file stock `> 0`.

The agreed quantity formula is **not** what VB or Nexora runs today. See `06_PROCUREMENT_RULEBOOK.md` and `07_LEGACY_VS_NEXORA_CONFLICT_MATRIX.md`.

## Highest-impact verified gaps

1. **VB recency is 10 days, hard-coded** in `FetchSourceData` (`DATEADD(day, -10, GETDATE())`). Agreed target is 15. Nexora default is also 10 (`decision_rules.py` `recency_days`). The Python legacy service default is 15 (`LEGACY_RECENCY_DAYS`). Three different clocks.
2. **`MaxSalesQtyInBill` is the largest sale line, not the bill total.** Local SQL: `MAX(Quantity)`. Max **day** is computed (`MaxSaleInfo`) and used for the WantedType label, not for `OrderQty`.
3. **Agreed gross target** (avg×18, max bill, max day, avg bill, minus `TotalStock`, minus confirmed supplier pending) matches neither engine. Nexora adds max day and max bill but uses `StockInHand` and does not subtract pending. VB uses max line only and `TotalStock`.
4. **`until_next_demand` is released by a new sale**, same predicate as `until_next_sales` (`order_items_repository.carry_forward_skips` 59–103). The suspected defect is present.
5. **Additional Row qty 1 is zeroed** after insert (`Form1.InsertDataIntoDestination` 6084–6087). Nexora keeps qty 1 (`INCLUDED_RARE_MOVER_TOPUP`).
6. **Delete** in VB and the Stock Client removes the row from the grid only. It is not disabled when the filter is All.
7. **Right Arrow in VB moves to the `free` column**, not to supplier selection (`dgvMain_KeyDown` 2181–2207). Supplier assign on the Stock Client is Enter when a supplier is selected.
8. **No live stock sample** of `TotalStock` vs `SUM(Batches.Stock)` vs `ProductTrans.StockInHand` was run. That comparison is UNKNOWN.

## Go / no-go

**NO-GO** for building the screen until the quantity profile in `12_APPROVAL_REQUIRED_DECISIONS.md` is locked and a fixture proves it against VB `FetchSourceData`. The smallest next step is that fixture, not UI.
