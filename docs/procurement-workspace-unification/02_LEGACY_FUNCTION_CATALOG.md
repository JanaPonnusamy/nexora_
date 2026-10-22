# 02 — Legacy VB.NET function catalog

File unless noted: `D:\VBDOTNET\OrderManagement\OrderManagement\Form1.vb`.  
Confidence: VERIFIED by reading the cited lines.

## Login and store

| Function | Lines | Behavior |
|---|---|---|
| `LoginForm.btnLogin_Click` | `LoginForm.vb` 5–42 | `SELECT UserID, Username, Role FROM Users WHERE Username=@username AND Password=@password`. Sets `UserSession`. Password compared in SQL. No hash visible in this method. |
| `UserSession` | `UserSession.vb` 1–6 | `UserRole` is an integer. Names Admin/PM are not in source. |
| `dgvStoreList` selection handler | `Form1.vb` 250–315 | Loads `stores` (`isactive=1`). Role 1 gets Process Order, Compare Previous Order, Supplier Excel Mapping, Integrate Order and Purchase, Access DB, plus the Role 2 set. Role 2 gets Auto Pur UpDate, Compare Supplier, Supplier Order Details, Pending Order, Supplier Invoice, Order Based Supplier Stock, Qty Check. Other roles get an empty process list. |
| `cboProcess_KeyPress` | 486–635 | Enter dispatches the mode. **Process Order** opens `PasswordPromptForm`, decodes a 13-char passcode, requires `TargetDate = today`, then sets `MinDays`/`MaxDays` and calls `ProcessOrder`. |

## Generation

| Function | Lines | Behavior |
|---|---|---|
| `ProcessOrder` | 6182–6196 | Requires source server fields. Starts `BackgroundWorker1` with `FetchOrderData`. |
| `FetchSourceData` | 5987–6029 | Inline SQL. `@ODATA` from caller (90-day window is set by the worker; the SQL divides by hard-coded `90.0`). `@minday`/`@maxday` from the passcode. `@status=0`. |
| `InsertDataIntoDestination` | 6034–6088 | `INSERT OrderManagementBackup SELECT *`, `DELETE` store rows, bulk copy, then `UPDATE ... WantedType='Additional Row'` sets `OrderQty=0, OrgOrderQty=0, Status=2, Remarks='Additional'`. No explicit SQL transaction around the four steps (three commands + bulk copy on one open connection). Failure mid-way is UNKNOWN without a test. |
| `UpdateOrderHeaderDetails` | 6091+ | Last `C%` bill, last `InvoiceSeries='IV'` GRN, inserts `OrderHeaderDetails` with min/max days. |

### Local SQL facts inside `FetchSourceData` (5997)

Sales CTE: `Transactiondate >= @ODATA`, `quantity > 0`, `SeriesTransID = 1`, `transactionvalidity = 0`, `isactive = 1`, `DontConsiderInOrder = 0`, store scoped. `Frequence = COUNT(DISTINCT ps.ID)`.

```
minqty = MAX(CEILING((slsqty/90)*@minday), CEILING(slsqty/Frequence))
maxqty = MAX(CEILING((slsqty/90)*@maxday), MaxSalesQtyInBill)
MaxSalesQtyInBill = MAX(Quantity)   -- one sale row, not a bill sum
Orderqty = 1 if TotalStock=0 and (maxqty-TotalStock)<=0
           else CEILING((maxqty-TotalStock)/SaleUnit) if SaleUnit>0
           else 0
WHERE lastsaledate >= today-10
  AND (maxqty-TotalStock)/SaleUnit > 0
  AND minqty > TotalStock
  AND lastsaledate >= LastReceivedDate
```

`lastsaledate` / `LastReceivedDate` come from `ProductTrans` where `LastBillDate >= today-20`.

`MaxSaleInfo` is `SUM(Quantity)` per product per `Transactiondate`, top day. Used in the **outer WantedType** (`Min & Max Based MaxsaleQTY`), not in `Orderqty`.

Remote branch (5994) hard-codes the same −10 day gate and divides by `SaleUnit` without the `> 0` guard.

Stock column in the formula: `products.TotalStock`. No `Batches.Stock`. No supplier-pending subtraction.

## Three ordering modes

| Mode | Loader | Lines | Rule |
|---|---|---|---|
| Qty Check | `LoadQtyCheckData` | 896–970 | `ordermanagement` where `qtycheck=0`, status 0, Pharma/Non Pharma, optional product type. Wanted-type combo via `LoadQtyCheckData_ByCombo`. |
| Auto Pur UpDate | `LoadDataForSupplier` | 3848–3870 | `OrderManagement` **inner join** `OrderPurchaseTrans` on product+store, supplier code in `SplitString`, `OrderQty>0`, status 0. History match, not live stock. |
| Supplier Stock | `LoadDataForSupplierStock` | 4228–4281 | Join `SupplierProductMatch` and `SupplierStock`. Requires `SS.Stock > 0`. Shows supplier stock, discount, scheme, free, rack. |
| Pending Order | process case 511–530 | separate query path `HandlePendingOrder` 3997 | Product type + supplier search. Not fully re-read this pass. |

## Quantity, keys, delete

| Handler | Lines | Behavior |
|---|---|---|
| `dgvMain_CellBeginEdit` | 1867–1872 | Only column index 3 (OrderQty) is editable at begin-edit. |
| `dgvMain_CellEndEdit` | 1875–1904 | Builds remark (`Don't Want to Order` if 0) and calls `UpdateDatabase(code, qty, remark)`. |
| `UpdateDatabase(code, qty, remark)` | 2315–2356 | Updates only when remarks were null or stored qty differs. |
| `UpdateValues` | 1489–1509 | `SET orderqty, remarks, qtycheck=1` where status 0. |
| `UpdateDatabase(code)` | 2380–2518 | **Returns immediately if process is Qty Check.** Otherwise toggles `status` 0↔1 and writes `orqty`, `orsupplier`, `orsuppliercode`. Pending Order writes supplier name `Pending Order` and code `pending`. |
| `dgvMain_KeyDown` | 2098–2233 | Enter: end edit, `UpdateDatabase(code)` (no-op on Qty Check), `HandleCellValueChange`, next row. Esc: cell=0, `UpdateDatabase(code, 0, "Don't want to Order")`, next row. Up/Down: `HandleCellValueChange` then move. `HandleCellValueChange` (1909) only calls the qty update when the parsed value **equals** the current cell value. Down does not by itself run `CellEndEdit`. Delete: `DeleteCurrentRow`. Right: focus column `free` and begin edit. |
| `DeleteCurrentRow` | 2295–2298 | `dgvMain.Rows.Remove` only. No SQL. Not disabled for All. Not limited to two modes. |
| `ValidateOrderQty` | 1963–1970 | Integer `>= 0`. Not shown wired into `KeyDown`. |
| `MoveToNextRow` / `MoveToPreviousRow` | 2242–2260 | Moves to `OrderQty`. Last row logs and stays. |

Qty Check persistence path that is verified: `CellEndEdit` → `UpdateValues` (`qtycheck=1`). Enter on Qty Check does not call that overload.

## Compare, export, close

| Function | Lines | Behavior |
|---|---|---|
| `CompareOrderManagement` | 3872–3918 | From backup: copy assigned lines to status 2; mark reviewed zero-qty as status 2; if backup stock > current stock, `orderqty = OrgOrderQty − backup.orqty`, remark `After Order Sold`. |
| `CompareOrderManagementSupplierWise` | 6992 | Supplier-scoped compare. Body not fully re-read. |
| `btnExport_Click` | 4830 | Export selected grid columns. Body starts 4830; column picker and split live in `ExportSelectedColumnsFromGrid` 4585. |
| `IntegrateOrderAndPurchase` | 679–691 | Latest prior `OrderHeaderDetails` date, then `OrderProcess.UpdatePurchaseTrans4Order`. |

No function named close-order was found. Status 2 is the terminal line state used by compare and additional-row neutralization. A session-close object is UNKNOWN.

## Order identity

`OrderID` string: `yyyyMMdd` + minute + second (no hour in the VB expression at 5997). Product identity on the grid is `ProductCode` + `storename`. Assignment identity is the same row’s `status`/`orsuppliercode`, not a child table.
