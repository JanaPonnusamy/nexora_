# 04 — Stock Client and web keyboard audit

## Stock Client

File: `E:\Nexora\desktop\supplier-stock-client\src\App.jsx`, function `OrderWorkspace` (comment at ~3562). API: `desktop/supplier-stock-client/src/api/client.js` `/api/legacy-order/*`.

| Behavior | Evidence | Verified behavior |
|---|---|---|
| Qty Check ↑/↓ | `makeCommitQty` 4080–4089, key handler ~4129–4166 | Arrow **saves** via `legacyUpdateQtyCheck` (sets `qtycheck=1`) and moves focus immediately, before the response. |
| Qty Check Enter | ~4137–4151 | Calls the same qty-check API. Row is not removed in the client; the API still sets `qtycheck=1`. |
| Esc / empty Backspace | ~4152–4161 | Qty 0 and qty-check save. |
| By Supplier Enter | ~4816–4830 | If a supplier is selected and the line is unassigned, Enter assigns (`toggleAssign`) after saving qty. Otherwise saves order qty. |
| By Supplier Delete | 4831 `removeRow` | `removeRow` 4056–4058 adds the code to `removedCodes` and restores focus. **No API delete.** |
| Delete when filter is All | not found | **Not disabled.** |
| Right Arrow | not found on the qty input in the cited handlers | Supplier change is Enter, not Right Arrow. |
| +/- | 4821–4825 | Local increment only. |
| Store change | prior audit + workspace clear pattern | Client clears scoped rows when the store changes. Stale-response token: PARTIALLY VERIFIED (web page clears before fetch; Electron generation token was not re-proven line by line this pass). |
| Who sees the screen | `App.jsx` ~371–391 | Super admin or purchase-manager purchase-detail right. Role 2 equivalent is not the VB integer. |

Layout persistence for column hide exists (`App.jsx` ~3067 comment: each grid has its own column list). Reset and per-store scope: PARTIALLY VERIFIED (column state exists; store-scoped key not re-read).

## Web Order Workspace

`frontend/src/pages/legacy-order/OrderWorkspacePage.tsx`

| Key | Qty Review (~309–321) |
|---|---|
| Enter | PATCH qty-check, drop row from the unreviewed list, focus next |
| Esc | qty 0, same commit |
| ↑/↓ | Move **without** save |

Review-all / By Supplier (~409–427): Enter saves `PATCH /orders` if changed. Esc sets 0. Arrows move without the qty-check commit.

Web export does not send `product_codes` (prior audit, `legacyOrderService` + `order_export.py`). Desktop By Supplier export does. VERIFIED earlier; not re-executed.

## Nexora ProductGrid

`frontend/src/components/procurement/ProductGrid.tsx` 278–398.

| Key | Behavior |
|---|---|
| Enter, ArrowDown | Save if qty>0, else skip, then advance |
| ArrowUp | Move, no save |
| Esc on qty | Skip (`DEFAULT_SKIP_MODE` = `current_refresh`), **do not advance** |
| ArrowRight | Enter supplier zone (saves row first) |
| Enter in supplier zone | Assign highlighted supplier for the line, next product |
| Space | Toggle export checkbox, not defer |
| Ctrl/Cmd+F | Search, on `PurchaseWorkspacePage.tsx` |

## Conflict with the agreed keyboard target

Agreed: Up/Down **save** then move; Right Arrow changes supplier **as the Stock Client does**; Delete only in Auto Purchase Update and Supplier Stock, disabled on All; Esc skip only if verified and compatible.

Stock Client already saves on Up/Down in Qty Check. VB Up/Down do not reliably save (see catalog). Web Qty Review arrows do not save. Right Arrow is VB→`free` column, Nexora→supplier zone, Stock Client→not used. Delete is view-only in both VB and Stock Client and is not mode-gated.

Do not copy one handler onto the others without an explicit mode matrix. Proposed matrix is in `10_TARGET_ARCHITECTURE.md`.

## Order Workspace chrome (2026-10-25)

The Stock Client Order Workspace (`App.jsx` `OrderWorkspace`, class `ow-proc`) was restyled in place. The Procurement tab is a separate screen; its 2026-10-25 verification is the next section.

- Header shows Nexora Procurement / Order Workspace, the selected store, the existing process list (Qty Check, Pending Order, Auto Pur UpDate, Order Based Supplier Stock, Supplier Order Details), and the order number from `legacyOrderHeader` when that payload has one. `updated_at` is shown only when the payload includes it.
- The summary strip totals the rows currently listed. Original quantity is the sum of `orgorderqty` / `OrgOrderQty` and is omitted when the loader did not send that field. Final quantity includes unsaved edits. Qty 0 is a do-not-order count. Pending, Assigned, and Open come from the existing workflow payload.
- The side column leads with the selected line. Previous orders are not docked under the grid. Each product row has an info button that opens that line’s quantities and its previous orders. Assign on a supplier row still calls `toggleAssign`. It does not create a recommendation.
- Grid columns, quantity rules, the three loader queries, export card, column settings (`nexora.desktop.owGridColumns.v2`), and layout settings (`nexora.desktop.owLayout`) are unchanged. `owNormalizeLayout` still accepts an older save: missing row font stays Normal, and a missing panel is appended. S.No default width is 56px; a saved width still wins.
- Right Arrow still does not move to a supplier. Enter remains the supplier assign key on the By Supplier grid.
- Cross-branch “no sales for 180 days” is not shown. The order loaders do not return that network fact.

## Procurement tab — 2026-10-25 verification

Screen: `desktop/supplier-stock-client/src/ProcurementWorkspace.jsx`, launched with the repo Electron against the already-running Vite dev server and the healthy LAN API. No order line was saved, assigned, exported, or finalized.

| Gate | Status | Evidence |
|---|---|---|
| Procurement tab actually shows | **PASS** | `.ow-screen { display: flex }` was winning over `.ow-screen-hidden`, so Order Workspace stayed on screen and covered Procurement. `.ow-screen.ow-screen-hidden` now wins. CDP: Order Workspace `display:none` while Procurement is active, and the reverse when switching back. |
| Grid at 1366×768 | **PASS** | S.No column measured 56px. Product names such as ABZORB SOAP 100GM fit. Qty Check listed 772 rows. Wanted’s default width is 116px (a saved width still wins) and the cell `title` is the full value, so “Regular Order (90 Days Avg)” is readable when the column ellipsizes. |
| Supplier cards | **PARTIAL** | Best / Frequent / Latest / Live cards followed the selected product (ABZORB vs ACECLO PLUS). Assign stayed disabled at final qty 0. Discount from the payload is shown when present (8% on the ACECLO card). A live `ST_*` warehouse card was not in the products opened, so that refusal was checked by unit test only. |
| Latest GRN facts | **PASS** | ACECLO PLUS showed cost 61.06, PTR 81.42, MRP 106.87, discount 10%, received 10, free 2, supplier THANTHAI PHARMA DISTRIBUTOR, last sale 02/10/26, last GRN 26/08/26. ABZORB, which has no purchase history, showed em dashes rather than zeros. |
| Process tabs | **PASS** (read-only) | Qty Check 772, abnormal 48, Pending Order 11, Rejected 421. By Supplier and Supplier Orders stay empty until a supplier is picked. |
| Keyboard saves | **NOT VERIFIED** on live data | Up/Down, Enter, Esc, and Backspace call the qty-check API. They were not pressed. Quantity rules are covered by `procurementWorkspaceView.test.js` (zero kept, five-digit cap). |
| Settings | **PASS** | Gear opened the saved column list (show, move, width) and Tick/Text. Preferences were not reset. Row height/weight re-read `nexora.desktop.owLayout` when the screen is shown. |
| Export, WhatsApp, finalize, Device Controller | **NOT VERIFIED** as actions | Export, Remove out-of-stock, Finalize, and Reopen are still the existing handlers. None were run. Device Controller enrollment in `App.jsx` was not changed. |
| Installer | **BLOCKED** | `release/Axythic-Supplier-Stock-Setup-0.1.49.exe` (25 Oct 2026 10:42) is older than these source edits. No installer was built or published. |
