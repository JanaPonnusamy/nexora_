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
