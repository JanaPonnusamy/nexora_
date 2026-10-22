# 05 — Database and SQL audit

**Live database was not opened.** Objects below are those named by VB or Nexora SQL. Missing keys, triggers, and indexes are UNKNOWN unless a migration file in-repo states them.

## Identity fields used by code

| Concept | Authoritative object in code | Notes |
|---|---|---|
| Store | VB `stores.storename`, `storecode`. Nexora `tenant_id` + `store_id` | Not the same key. |
| Product | `ProductCode` + store | Integer code per store. Cross-store equality is not implied. |
| Sale line | `ProductSaleInformation` | Filters: `SeriesTransID=1`, `transactionvalidity=0`, `DontConsiderInOrder=0`, `quantity>0`. What validity `0` means beyond “included” is UNKNOWN (cancelled vs void vs edited). |
| Bill | VB does not group by bill number for frequency. Nexora groups by series\|bill\|date | Modified-bill duplicates: no revision key found. UNKNOWN. |
| Sale day | `Transactiondate` (VB groups the datetime value as stored; date-only cast not in the MaxSaleInfo GROUP BY) | If the column contains a time, two bills on one calendar day can split. PARTIALLY VERIFIED risk. Nexora casts `AS DATE`. |
| Physical stock (VB formula) | `products.TotalStock` | |
| Stock (Nexora formula) | `sync.ProductTrans.StockInHand` latest month | Documented as disagreeing with TotalStock. Sample not re-measured. UNKNOWN this session. |
| Batch stock | `Batches` imported by VB `ImportDataForBatches` | **Not referenced** by `FetchSourceData`. `SUM(Batches.Stock)` vs TotalStock is UNKNOWN. |
| Receipt | `PurchaseTrans.grndate`, `Grnnumber`, `FreeQty`, `InvoiceSeries` | VB header uses `InvoiceSeries='IV'`. Offer flag excludes `TI`. |
| Order header | `OrderHeaderDetails` | Order no per store per calendar day. |
| Order lines | `OrderManagement` | One row per store+product after delete/insert. `OrderId`, `OrderQty`, `OrgOrderQty`, `Status`, `QtyCheck`, `OrSupplier`, `OrSupplierCode`, `OrQty`, `Remarks`, `WantedType`. |
| History | `OrderManagementBackup` | Full row copy before delete. |
| Purchase link for Auto mode | `OrderPurchaseTrans` | Join in `LoadDataForSupplier`. Column list beyond the join was not re-read. |
| Supplier file stock | `SupplierStock`, `SupplierProductMatch` | |
| Nexora working line | `procurement.procurement_order_items` | `suggested_qty`, `final_qty`, `assigned_qty`, `remaining_qty`, `item_status`, `skip_reason`, `reviewed_at`. |
| Nexora VPL | `procurement.procurement_virtual_products` | Include rows only. |
| Nexora assignment / export | assignment tables used by `assignment_service` / `export_service` | Exported status is separate from `item_status`. Exact table name: see `assignment_repository.py` (not re-opened this pass). PARTIALLY VERIFIED. |
| Export template | `procurement.supplier_export_settings` | `format, columns, order_qty_header, sort_by, export_folder_path` keyed by tenant, store, supplier. No store-default table found. |
| Users (VB) | `Users(UserID, Username, Password, Role)` | Plain comparison in login SQL. |

## Pending quantity

VB order SQL does not read an outstanding PO balance.

Nexora `effective_available` can subtract reserved and add receivable, but `load_source` never loads those columns, so they are 0.

`reconciliation_rules.item_receipt_state`: pending = final − received, floored at 0. That is receipt math after export, not an input to suggested qty. Cancelled portal orders and receipt reversals are not in this function. UNKNOWN whether a reversal row exists.

## Transactions and audit

VB `InsertDataIntoDestination` is not wrapped in `BEGIN TRAN` in the method body. Backup, delete, and insert can diverge if the process dies after delete.

Nexora skip/final updates are single statements. Override reason is a column. A full before-image of every qty edit was not found (UNKNOWN beyond `manual_override` / `override_reason`).

VB writes text logs under `D:\OrderDotNet\Log\`. Those files can contain product codes and quantities. They are not a queryable audit table.

## Indexes known from Nexora legacy migrations

`backend/modules/legacy_order/sql/0005_order_calc_perf.sql`, `0006_qty_check_sidebar_indexes.sql`. VB Form1 does not create them. Whether production has them is UNKNOWN.
