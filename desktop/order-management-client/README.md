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
   - **Pending Order Qty Check** — `dgvMain` = the pending lines; edit *OrderQty*
     inline (reviewed lines drop off).
   - **Auto Pur UpDate** — supplier history: search a supplier (`dgvSupplierList`),
     then `dgvMain` = its orderable lines by purchase history.
   - **Order Based on Supplier Stock** — the same but matched to live SupplierStock.
3. Selecting a product row fills the right side — `dgvPurchaseDetails`,
   `dgvSalesDetails`, and **`Chart1`** (monthly Purchase=blue / Sales=green /
   Stock=red), with the `Local DB` / `Remote DB` source toggle.
4. **Export** builds the supplier order to Excel.

Interactive actions available: edit OrderQty / qty-check review and export. The
head-office-only controls (Sync, Pull, Mapping, Web Export, Import Stock, Split
Excel) are present for visual fidelity but explain that they run in the HO
console; the batch triggers (Sync / Order-Process / Stock-Update) are not in
this client.

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
