# Nexora Order Management (lightweight desktop client)

A tiny native Windows client for the legacy **OrderManagement** screen that works
from **anywhere** (outside the store LAN) by talking to the HO backend over the
internet. It reads and writes order data **only** through Nexora's
`/api/legacy-order/*` HTTP API — it never opens a direct connection to the
OrderNMC database, and it changes nothing in the existing LAN/legacy app.

The UI is a **faithful replica of the VB `Form1`**: the same single maximized
window, the same controls at the same positions (copied from
`Form1.Designer.vb`), the same blue background, and the same monthly
Purchase/Sales/Stock column chart. `src/OrderForm.cs` lays everything out with
the exact VB coordinates.

Flow (same as the VB app):

1. **Select Store** (`txtStoreSearch` + `dgvStoreList`) — admin picks any store; a
   store user is locked to their own.
2. **Select Process** (`cboProcess`):
   - **Pending Order Qty Check** — `dgvMain` = the pending lines; the **Or Qty**
     column is highlighted green and is the only editable cell. **Enter** saves
     the typed quantity; **Esc** = "Don't Want to Order" (sets 0). Reviewed lines
     drop off the grid, and the first row opens in edit mode for fast entry.
   - **Auto Pur UpDate** — supplier history: search a supplier (`dgvSupplierList`),
     then `dgvMain` = its orderable lines by purchase history.
   - **Order Based on Supplier Stock** — the same but matched to live SupplierStock.
   - **Supplier Order Details** — the order already placed with a supplier
     (assigned lines), ready to export.
3. Selecting a product row fills the right side — `dgvPurchaseDetails`,
   `dgvSalesDetails`, and **`Chart1`** (monthly Purchase=blue / Sales=green /
   Stock=red).
4. **Export** writes the current grid to an Excel-openable CSV (works for any
   view, including an already-placed Supplier Order Details order).

Columns use the same headers/formats as the VB form: friendly headers, hidden
ProductCode, a `#` serial column, **quantities as whole numbers (N0)** and prices
to two decimals (N2). The only button is **Export** — every head-office-only
control (Sync / Pull / Mapping / Web Export / Import Stock / Split Excel) is
removed; this is a read-and-export client.

## Why it's tiny

- Native **C# WinForms**, compiled by the in-box `csc.exe` (.NET Framework 4.x) —
  no .NET SDK, no Visual Studio, no runtime to install.
- JSON via the in-box `System.Web.Extensions` (`JavaScriptSerializer`) — **no
  vendored DLLs**. The build output is a single `NexoraOrderManagement.exe`.
- Runs on any Windows 7 SP1+/10/11 that has the (preinstalled) .NET Framework.

## Build

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
# -> bin\NexoraOrderManagement.exe
```

## Configure / run

On first launch the sign-in dialog asks for the HO address and your login. These
are saved to `%APPDATA%\NexoraOrderManagement\config.json` (see
`config/config.sample.json`):

- `ho_urls` — ordered list of HO endpoints to try at sign-in (public NAT first,
  LAN fallback). The address you type at login is moved to the front.
- `allow_insecure_tls` — accept the HO server's TLS certificate even if it is
  self-signed (the public HTTPS endpoint typically is).

## Access model

- **Store user** (e.g. an NMV purchase manager): can view and work **their own
  store's** order (edit / qty-check / assign / export). Scoped and enforced
  server-side.
- **Admin / platform user**: can pick any store from the top bar.

Non-order-console actions and other stores are refused by the backend regardless
of what the client sends.
