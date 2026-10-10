# Nexora Order Management (lightweight desktop client)

A tiny native Windows client for the legacy **OrderManagement** screen that works
from **anywhere** (outside the store LAN) by talking to the HO backend over the
internet. It reads and writes order data **only** through Nexora's
`/api/legacy-order/*` HTTP API — it never opens a direct connection to the
OrderNMC database, and it changes nothing in the existing LAN/legacy app.

It mirrors the two VB `Form1` processes a purchase manager actually uses, with
the product **detail panel** docked on the right as in the original:

| Screen | VB equivalent | What it does |
|---|---|---|
| **Qty Check** | Pending Order Qty Check | Review the pending lines; edit *OrderQty* inline or mark a line "Don't Want" (0). Reviewed lines drop off the grid. |
| **Supplier Ordering** → *Auto Pur UpDate* tab | `LoadDataForSupplier` (history) | A supplier's orderable lines by purchase history. |
| **Supplier Ordering** → *Order Based on Supplier Stock* tab | `LoadDataForSupplierStock` (stock) | A supplier's orderable lines matched to its live SupplierStock. |
| **Product Detail Panel** (right) | Form1 detail tabs | Purchase / Sales / Monthly stats / Order history for the selected product. |

Interactive actions available: edit OrderQty, qty-check review, assign a line to a
supplier, and export the order to Excel. The batch triggers (Sync / Order-Process
/ Stock-Update) stay HO-admin-only and are intentionally **not** in this client.

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
