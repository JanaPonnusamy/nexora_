# 08 — Order and portal sequence diagrams

Functions named here were read in source. Steps marked UNKNOWN were not found.

## VB — start an order

```
LoginForm.btnLogin_Click
  -> Users.Role -> UserSession.UserRole
Form1 store grid
  -> stores row -> server, database, storeName
cboProcess_KeyPress "Process Order"   (Role 1 menu only)
  -> PasswordPromptForm
  -> PasswordDecoder.DecodeCompactPasscode
  -> reject if TargetDate <> today
  -> MinDays, MaxDays
  -> ProcessOrder
  -> BackgroundWorker1 FetchOrderData
  -> FetchSourceData (local or remote SQL)
  -> InsertDataIntoDestination
       backup OrderManagementBackup
       delete OrderManagement for store
       bulk insert
       zero Additional Row
  -> UpdateOrderHeaderDetails
```

## VB — Qty Check then assign

```
cboProcess "Qty Check"
  -> LoadQtyCheckData (qtycheck=0, status=0)
dgvMain_CellEndEdit
  -> UpdateDatabase(code, qty, remark)
  -> UpdateValues (orderqty, remarks, qtycheck=1)
Enter on a non-Qty-Check process
  -> UpdateDatabase(code)
  -> status 0->1, orqty, orsupplier, orsuppliercode
     or status 1->0 clear supplier
```

Auto Pur UpDate does not recalculate qty. It filters with `LoadDataForSupplier`.
Supplier Stock filters with `LoadDataForSupplierStock` (`SS.Stock > 0`).

## Nexora — refresh to export

```
orchestration refresh
  -> decision_repository.load_source
  -> decision_rules.evaluate
  -> decision_service.generate_vpl (INCLUDE only)
  -> order_items_repository.generate_working_items
  -> carry_forward_skips
PurchaseWorkspacePage loads workspace + recommendations
ProductGrid Enter -> set_final_qty
ProductGrid supplier Enter -> assignment_service (one supplier)
export_service.export_refresh -> batch EXP-...
GRN submit -> reconciliation_rules.assignment_state
```

## Agreed target — not implemented

```
Admin: start order (new id, Profile = agreed formula, stock = TotalStock)
PM: Qty Check | Auto Purchase Update | Supplier Stock
    edit final qty (auto-save)
    assign (manual wins)
    pending / not supplied
PM: submit
Admin: export Excel (template precedence) OR place portal (worker)
Receipt: received qty from GRN lines, not from the GRN number alone
Close: allowed with outstanding deliveries after assigned-work summary
```

## OrderBot — portal only, not called by Nexora

`D:\VBDOTNET\OrderBot\main.py`

```
make_driver (Chrome, webdriver-manager)
load_cookies OR login (UserName, Password, optional Tkinter OTP)
select_distributor_store (hard-coded Nathan option in config xpaths)
for sku, qty in products.csv:
    add_product (search, first result, srqty, AddToCart)
    on no result: CSV status "Stock Not Available"
ask_confirmation (Tkinter)
place_order -> click ConfirmOrder
driver.quit
```

No portal order number is parsed. `place_order` logs success after the click (main.py 188–190). That is not confirmation evidence.

`config.json` `base_url` is `https://www.pharmarack.com`. Cart URL is `/Retailers/OrderCart/Create`. README also names `westernsalem.retailorders.in`. That URL is not in `config.json`. Support for Western Salem is UNKNOWN.

`D:\VBDOTNET\PY` does not appear in this sequence. `p4.py` logs into Purani ERD and downloads invoices.

## Safe integration boundary

```
Electron "Place on portal"
  -> POST job {export_batch_id, supplier_code}   [proposed, does not exist]
  -> worker claims job if no running job for that browser profile
  -> Playwright adapter.place(lines) -> {portal_order_id | failed, per line}
  -> persist status
  -> UI polls job
Grid final_qty is not an input the adapter may write.
```

Selenium `main.py` stays runnable by hand until the adapter reproduces login, distributor select, search, qty, add, and a real confirmation read.
