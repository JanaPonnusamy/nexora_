# Phase 1 — source field map (task P1-B)

**Status:** documentation only. No Python, SQL, UI, or migration file
edited. No production database queried. Owner: CLAUDE. Task: P1-B per
`AUTONOMOUS_WORK_CONTROL.md`.

Maps the actual source evidence for the three legacy-order loaders —
Qty Check, Auto Purchase Update, Supplier Stock — plus stock source,
SaleUnit/pack handling, pending quantities, and `DontConsiderInOrder`.
Every fact below is tied to a file path and function/SQL reference actually
read in this pass; anything not confirmed is marked **UNKNOWN**.

---

## 1. Qty Check

**Function:** `repository.qty_check_rows(store_name)` —
`backend/modules/legacy_order/repository.py:1036-1061`.
**Port of:** `Form1.GetQtyCheckQuery('All', 'All')` (legacy VB, not
re-read in this pass — relying on the existing in-code docstring, which
names the VB entry point).
**Filter:** `om.qtycheck = 0 AND om.status = 0 AND om.storename = ?` —
only rows not yet PM-reviewed.

Fields returned (all from `OrderManagement` unless noted):
`productcode, productname, orderqty, orgorderqty, totalstock, saleunit,
unitdescription, slsqty, mrp, lastreceiveddate, lastsaledate, maxsaleqty,
Transactiondate, wantedtype, producttypename, remarks, IsOffer,
LastOfferBaseQty, LastOfferFreeQty`.

- `LastOfferBaseQty`/`LastOfferFreeQty` are the only **live** read in this
  query — an `OUTER APPLY` against `PurchaseTrans` (`_LAST_OFFER_PATTERN_APPLY`,
  `repository.py:678-690`), grouped by `Grnnumber` and summed before taking
  the most recent GRN, specifically to avoid misreading a supplier invoice
  whose free-qty line is split across multiple `PurchaseTrans` rows (code
  comment cites a confirmed live case on NMS, 2026-10-17, GRN 11783).
- Every other field is a **snapshot frozen at order-generation time**
  (written by `order_local.sql`/`order_process.py`, not re-read live).
- No supplier-assignment field in this payload. Assignment is a separate
  write path (`assign_supplier`, `bulk_assign_rows` — not read here).

## 2. Auto Purchase Update

**Function:** `repository.orders_by_supplier(store_name, supplier_code,
mode="history")` — `backend/modules/legacy_order/repository.py:693,
741-781`.
**Port of:** `Form1.LoadDataForSupplier`, with one **documented, in-code**
deliberate divergence: the VB source read `OrderPurchaseTrans` (a
legacy-only staging table); this port reads `PurchaseTrans` (the real,
actively-synced GRN/invoice table) instead, because `OrderPurchaseTrans`
has no freshness guarantee in this environment (`repository.py:711-720`).

**Filter:** `om.Status = 0 AND om.OrderQty > 0 AND om.ProductTypeName IN
('Pharma','Non Pharma') AND om.StoreName = ?` AND an `EXISTS` against
`PurchaseTrans` for this product/store from this supplier,
`pt.InvoiceSeries <> 'TI'` (excludes internal warehouse transfers —
see repo-wide "TI transfer vs supplier collision" convention cited in the
same docstring).

**Columns:** `_WORKSPACE_COLS` (`repository.py:651-656`) + `om.IsOffer`:
`ProductCode, ProductName, OrderQty, OrgOrderQty, TotalStock, SLSQty,
UnitDescription, SaleUnit, MRP, WantedType, Remarks, PurchasePrice,
SubLocation, ProductTypeName, MaxQty, Status, Qtycheck, IsOffer`.

**Known, documented data-quality gap (not a Phase 1 defect to fix):** a
real-world supplier can have multiple `OrderSuppliers` rows under
different `SupplierCode`s (e.g. NMV's several "Purani" entries). The
history-restriction filter is intentional — an owner trial on 2026-10-13
removed it and showed every open product regardless of supplier,
confirmed wrong live. Picking the wrong duplicate code can legitimately
show 0 history for a product that supplier does carry. Flagged for
Phase 7 (supplier assignment/Suggestion Box), out of scope here.

## 3. Supplier Stock Availability

**Function:** same entry point, `mode="stock"` branch —
`repository.py:721-740`.
**Port of:** `Form1.LoadDataForSupplierStock`.

**Filter:** `OrderManagement` → `SupplierProductMatch`
(ProductCode+StoreName+SupplierCode) → `SupplierStock`
(SupplierProductCode+SupplierCode+StoreName), `WHERE om.status = 0 AND
om.orderqty > 0 AND SS.Stock > 0` — only products with live
portal/file stock greater than zero for this supplier.

**Columns:** the Mode-1-style base fields (`ProductCode, ProductName,
OrderQty, OrgOrderQty, TotalStock, SLSQty, UnitDescription, SaleUnit, MRP,
WantedType, Remarks, PurchasePrice, SubLocation, ProductTypeName, MaxQty,
Status`) plus supplier-stock-specific: `S_Stock` (supplier's live stock),
`Discount`, `MinQty` (supplier minimum order qty), `Sch` (scheme), `Free`
(free-qty offer), `SupplierProductName`, `SupplierProductCode`, `Rack`,
`IsOffer`.

**`is_warehouse_stock` flag** — computed in Python, not SQL
(`repository.py:792-795`): `True` when `supplier_code == store["ho_code"]`,
meaning the row is NMW warehouse stock bridged in via
`sync_supplier_product_match_from_mapping` (part of Cursor's current
uncommitted `refresh_warehouse_stock` work in `order_process.py`), not a
real external supplier. This flag exists specifically so the UI can
distinguish warehouse-backed rows from genuine supplier stock.

---

## Stock source

**Confirmed:** `OrderManagement.TotalStock` in all three modes — a
**snapshot frozen at order-generation time** (written once by
`order_local.sql`/`order_remote.sql`, not re-read from live `products` or
`ProductTrans` on every grid load). This matches the master-prompt's
confirmed "Physical stock for the agreed target profile:
`Products.TotalStock`" — consistent, but note the UI reads the frozen
copy, not a live value. A future phase that wants live stock on the grid
would need a new read; none of the three loaders above do this today.

## SaleUnit / pack

All three modes expose `SaleUnit` directly off `OrderManagement` (frozen
at generation). None of the three loaders perform pack math themselves —
`OrderQty`/`OrgOrderQty` are already pack-ceilinged values written by
`order_local.sql`'s `Orderqty` CASE expression at generation time
(see `backend/modules/legacy_order/sql/order_local.sql`, the
`CASE WHEN ps.TotalStock = 0 AND (ps.maxqty - ps.TotalStock) <= 0 THEN 1
WHEN ps.SaleUnit > 0 THEN CEILING((ps.maxqty - ps.TotalStock) / ps.SaleUnit)
ELSE 0 END AS Orderqty` clause, already documented in
`00_EXECUTIVE_SUMMARY.md` L-04). None of the three read-side loaders
re-validate `SaleUnit <= 0`/null at read time — that gate exists only at
generation. **UNKNOWN:** whether the desktop/web UI additionally blocks
editing or exporting a row whose `SaleUnit` is 0/null; not verified in
this pass (would require reading `App.jsx`'s qty-editing handlers, which
are Cursor-owned active WIP and were not opened here per the file-ownership
boundary).

## Pending quantities

**Confirmed absent.** None of the three loaders read or expose any
`confirmedSupplierPendingQty`-equivalent column. No pending/in-transit/
reserved field exists in `_WORKSPACE_COLS` or either `mode="stock"` branch.
This matches the finding already on record in `AUTONOMOUS_WORK_CONTROL.md`
("Confirmed-supplier-pending source column — no single verified source
exists in either engine today"). Still blocked. The master prompt's net
formula (`gross - Products.TotalStock - confirmedSupplierPendingQty`) has
no real data source for the third term today in the legacy_order module;
a future phase must either locate one or keep it at 0 and say so in the UI
— per the master prompt's explicit "never fall back"/"no speculative data"
rule, this must not be silently assumed as 0 without surfacing it.

## DontConsiderInOrder

**Confirmed, generation-time only.** `order_local.sql`'s `SalesQuantity`
CTE filters `ps.DontConsiderInOrder = 0` when building the 90-day sales
sum that feeds `minqty`/`maxqty` (per `00_EXECUTIVE_SUMMARY.md` / audit
L-01 — not re-extracted line-by-line in this pass since the clause is
already quoted verbatim there and the SQL file itself was read in the
prior audit turn of this session). This is a **line-level** sales
exclusion inside generation, not a product-level flag checked by any of
the three read loaders above — none of `qty_check_rows` or
`orders_by_supplier` filter on `DontConsiderInOrder` themselves, because by
the time a product reaches `OrderManagement` the excluded sales lines have
already been removed from its `slsqty`/`minqty`/`maxqty` math upstream.
**Known documented gap (audit RULE-, "DontConsider with sales still passed
in"):** `PHASE_0_STATUS.md`'s three-way fixture table records that the
legacy SQL "still orders 1" in a case meant to be excluded, because
`order_local.sql` has no **product-level** `DontConsiderInOrder` flag check
— only the line-level sales filter. This is a pre-existing, already-known
discrepancy, not a new finding; not re-verified against live data in this
pass.

## Role 1 / Role 2

**Deliberately left unmapped**, per the master-prompt instruction and
`AUTONOMOUS_WORK_CONTROL.md`'s existing blocker: "Role 1/Role 2 → Admin/PM
mapping — still unconfirmed, blocked per master prompt §Phase 12." None of
the three loaders above take a role parameter. Not addressed further here.

---

## Explicit UNKNOWNs carried from this pass

1. Whether the desktop/web UI blocks editing/export on `SaleUnit <= 0`/null
   at the read/edit layer (vs. only at generation) — not verified; would
   require opening Cursor-owned `App.jsx`/`OrderWorkspacePage.tsx`, out of
   scope for this read-only, non-Cursor-file task.
2. `transactionvalidity` mapping for cancelled/modified bills — not
   re-verified in this pass; remains UNKNOWN per `PHASE_0_STATUS.md`.
3. A real source column/table for `confirmedSupplierPendingQty` — none
   found in the three loaders read in this pass. Still blocked.
4. Exact router paths in `backend/modules/legacy_order/router.py` that front
   these three repository functions — not re-diffed in this pass since that
   file is Cursor's active uncommitted WIP; confirm with Cursor before
   Phase 3 wires new UI to them.

## Sources read for this document

- `backend/modules/legacy_order/repository.py` (lines 651-797, 1036-1061)
- `docs/procurement-workspace-unification/PHASE_0_STATUS.md` (three-way
  fixture table, referenced not re-derived)
- `docs/procurement-workspace-unification/00_EXECUTIVE_SUMMARY.md` (L-01,
  L-04 citations, referenced not re-extracted)
- `docs/procurement-workspace-unification/AUTONOMOUS_WORK_CONTROL.md`
  (existing blockers, referenced not re-derived)
- `docs/procurement-workspace-unification/contracts/Procurement_Workspace_Master_Phase_Prompts.md`
  (confirmed identical to the document already read in full this session)

No Python, SQL, UI, or migration file was edited to produce this document.
No production database was queried.
