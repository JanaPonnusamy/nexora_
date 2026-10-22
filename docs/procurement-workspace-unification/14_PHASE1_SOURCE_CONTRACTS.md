# 14 — Phase 1 source data contracts (three modes)

**Status:** documentation only. No API, migration, or production behavior
changed. Read-only task per `AUTONOMOUS_WORK_CONTROL.md` (CLAUDE, Phase 1).

Maps the exact fields each of the three loaders returns today, from the
actual repository code — not invented. All three read `OrderManagement`
(central `OrderNMC` DB via `database.get_central_connection()`), scoped by
`StoreName`. None of the three write anything; all are read paths behind the
existing `/api/legacy-order/*` router.

## Mode 1 — Qty Check

**Function:** `repository.qty_check_rows(store_name)` (`repository.py:1036`).
**Port of:** `Form1.GetQtyCheckQuery('All', 'All')`.
**Filter:** `om.qtycheck = 0 AND om.status = 0 AND om.storename = ?` — only
rows not yet reviewed.

| Field | Source | Notes |
|---|---|---|
| `productcode`, `productname` | `OrderManagement` | |
| `orderqty`, `orgorderqty` | `OrderManagement` | `orgorderqty` is the immutable generated value; `orderqty` is PM-editable (RULE-103) |
| `totalstock` | `OrderManagement.TotalStock` | snapshot taken at generation time, **not** live `products.TotalStock` |
| `saleunit`, `unitdescription` | `OrderManagement` | |
| `slsqty` | `OrderManagement.SLSQty` | 90-day window sales qty, frozen at generation |
| `mrp` | `OrderManagement` | |
| `lastreceiveddate`, `lastsaledate` | `OrderManagement` | frozen at generation, from `ProductTrans` join inside `order_local.sql` |
| `maxsaleqty`, `Transactiondate` | `OrderManagement` | the max-day-sum figure and its date |
| `wantedtype` | `OrderManagement` | label only (RULE-102), not a quantity |
| `producttypename` | `OrderManagement` | `Pharma` / `Non Pharma` |
| `remarks` | `OrderManagement` | PM free-text / auto notes (`Don't Want to Order`, etc.) |
| `IsOffer` | `OrderManagement.IsOffer` | set once per product at generation (migration 0007 perf fix), not recomputed per row |
| `LastOfferBaseQty`, `LastOfferFreeQty` | live `OUTER APPLY` against `PurchaseTrans` | most recent GRN's received+free qty, grouped by `Grnnumber` to avoid misreading a split invoice line (see code comment) — this one field is **not** frozen; it reflects current purchase history at read time |

**No supplier assignment fields in this mode's payload.** Qty Check is
suggestion-review only, consistent with the master prompt's "Qty Check uses
manual supplier assignment" but assignment itself happens through a
different call (`assign_supplier`/`bulk_assign_rows`), not from this read.

## Mode 2 — Auto Purchase Update (`orders_by_supplier(mode="history")`)

**Function:** `repository.orders_by_supplier(store_name, supplier_code, "history")`
(`repository.py:693`, non-stock branch at line 741).
**Port of:** `Form1.LoadDataForSupplier` — **deliberately diverges** from the
VB source: VB used `OrderPurchaseTrans` (legacy-only staging table); this
port uses `PurchaseTrans` (the real, actively-synced GRN/invoice table),
because `OrderPurchaseTrans` has no freshness guarantee in this environment.
This divergence is already documented in-code, not a new finding.

**Filter:** `om.Status = 0 AND om.OrderQty > 0 AND om.ProductTypeName IN
('Pharma','Non Pharma') AND om.StoreName = ?` AND `EXISTS` a `PurchaseTrans`
row for this product/store from this supplier, `InvoiceSeries <> 'TI'`
(excludes internal warehouse transfers — see "TI transfer vs supplier
collision" memory).

**Columns:** `_WORKSPACE_COLS` (`repository.py:651`) + `om.IsOffer`:

`ProductCode, ProductName, OrderQty, OrgOrderQty, TotalStock, SLSQty,
UnitDescription, SaleUnit, MRP, WantedType, Remarks, PurchasePrice,
SubLocation, ProductTypeName, MaxQty, Status, Qtycheck, IsOffer`

Same frozen-at-generation semantics as Mode 1 for `TotalStock`/`SLSQty`.
`supplier_code` can be a comma-joined list (split in Python, not SQL — a
documented perf fix to keep the `PurchaseTrans` predicate sargable).

**Known data-quality gap (documented, not fixed in Phase 1):** a real
supplier can have several `OrderSuppliers` rows with different
`SupplierCode`s under the same name (e.g. NMV's multiple "Purani" entries).
Picking the wrong one legitimately shows 0 history for a product that
supplier does carry. This is out of scope for Phase 1; flagged here so the
UI/Phase 7 (Suggestion Box / supplier assignment) doesn't mistake it for a
formula bug.

## Mode 3 — Supplier Stock Availability (`orders_by_supplier(mode="stock")`)

**Function:** same entry point, `mode="stock"` branch (`repository.py:721`).
**Port of:** `Form1.LoadDataForSupplierStock`.

**Filter:** joins `OrderManagement` → `SupplierProductMatch` (by
ProductCode+StoreName+SupplierCode) → `SupplierStock` (by
SupplierProductCode+SupplierCode+StoreName), `WHERE om.status = 0 AND
om.orderqty > 0 AND SS.Stock > 0` — only products with **live portal/file
stock greater than zero** for this supplier.

**Columns:** `ProductCode, ProductName, OrderQty, OrgOrderQty, TotalStock,
SLSQty, UnitDescription, SaleUnit, MRP, WantedType, Remarks, PurchasePrice,
SubLocation, ProductTypeName, MaxQty, Status` + supplier-stock-specific:
`S_Stock` (supplier's live stock), `Discount`, `MinQty`
(supplier minimum order qty), `Sch` (scheme), `Free` (free-qty offer),
`SupplierProductName`, `SupplierProductCode`, `Rack`, `IsOffer`.

**`is_warehouse_stock` flag:** appended in Python (not SQL) — `True` when
`supplier_code == store["ho_code"]`, i.e. the row is actually NMW warehouse
stock bridged in via `sync_supplier_product_match_from_mapping` (Cursor's
current uncommitted `refresh_warehouse_stock` work), not a real external
supplier. UI must render this distinctly per the master prompt's
"non-moving warnings"/Suggestion-Box intent — this flag already exists for
that purpose.

## Cross-mode notes for Phase 2/3

- All three modes share one underlying row shape (`OrderManagement` plus
  mode-specific joins) — no separate VPL table exists yet. Phase 2's VPL
  working table should be designed so these three queries can be rewritten
  against it without changing the field names PM already sees.
- **Stock source confirmed for Phase 1 purposes:** `OrderManagement.TotalStock`,
  a **frozen snapshot taken at order-generation time**, not a live read of
  `products.TotalStock` and not `ProductTrans.StockInHand`. This matches the
  master prompt's "Physical stock for the agreed target profile:
  `Products.TotalStock`" — confirmed consistent, but note it is the
  generation-time snapshot, not live-queried per grid load. If a future
  phase wants live stock on the grid, that is a new read, not already present.
- **Pending source:** confirmed **not present** in any of the three loaders
  above. No column here represents `confirmedSupplierPendingQty`. This
  remains the blocker recorded in `AUTONOMOUS_WORK_CONTROL.md` — Phase 2/3
  must either locate a real source (none found in this pass) or keep the
  term at 0 and say so in the UI, per the master prompt's "never fall
  back"/"no speculative" rules.
- **`transactionvalidity` mapping:** not re-verified in this pass; remains
  UNKNOWN per `PHASE_0_STATUS.md`. Not re-litigated here.
- **Role mapping (Role 1/Role 2 → Admin/PM):** out of scope for Phase 1;
  none of the three loaders above take a role parameter today.

## Acceptance against Phase 1's gate

Per `Procurement_Workspace_Master_Phase_Prompts.md` Phase 1: "document the
approved generation profile and parameter snapshot... identify required
read models/endpoints without implementing UI... confirm stock source,
pending source, transaction validity, date semantics." This document
satisfies the source-field-map and stock/pending-source confirmation parts
using the three loaders that already exist and already match the
master-prompt's three named modes — no new endpoint was required because
`/api/legacy-order/*` already exposes exactly these three reads (confirm with
Cursor which router paths front them before Phase 3 wires the new UI to
them, since that router file is currently Cursor's active WIP and was not
re-diffed line-by-line in this pass).
