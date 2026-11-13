# 31 — Phase 7B collapse duplicate screens
**NEXORA MEDIQ — Stock Enquiry and one ordering screen**
Date: 2026-11-13

## 1. Decisions this sub-phase implemented

From the 7A review (doc 30, commit `2e18004`):

- Extend the Electron app only. The 31 web pages with no Electron screen stay a backlog. The web app was not changed and was not decommissioned.
- Stock: fold Network Stock's Batch/MRP search into the vertical screen, rename it **Stock Enquiry**, then delete the other two stock screens.
- Orders: remove Order Workspace. Keep Procurement Workspace as the ordering UI. Order Entry and Legacy Order stay.

## 2. Stock Enquiry

`stock_vertical` is still the screen id (role filters and the post-login landing already used it). The label is now Stock Enquiry.

The screen has two search modes:

- Product: the existing name/code search, including `*` wildcard and the offline product index.
- Batch / MRP: batch number, MRP, and product name, via the existing `searchStockBatches` API. That search has no local index, so a failed request stays an error instead of pretending the name cache is a batch result.

Removed from `screens`, `erpNav.js`, and the render tree:

- `stock` (horizontal Stock Availability)
- `network_stock` (Network Stock)

`StockAvailability` and `NetworkStockView` were deleted from `App.jsx` (1,590 lines). An unmatched screen now renders Stock Enquiry. The stock-viewer, stock-and-label, and SMS purchase-manager filters already named `stock_vertical` only; they were not rewritten.

The Network Stock page CSS (`.network-stock-screen`, `.ns-*`) is still in `styles.css`. Stock Enquiry reuses the `.ns-search__tab` rules for the mode tabs. The rest of that block is unused.

## 3. Order Workspace removed

`order_workspace` is gone from the nav, the permission filter, and the keep-mounted render. `OrderWorkspace.jsx` is deleted.

Procurement Workspace stays, including the shared pieces it already imported (`OwSharedControls.jsx`, `OwFormatters.js`, `OwDocumentCard.jsx`, `OwIntelligencePanel.jsx`, `OwExportKit.js`). Those files are not Order Workspace's private copy.

Order Entry's blocked-order action now says **Open Procurement** and switches to `procurement_workspace`. Legacy Order is unchanged, including the compare mode buried inside it. A standalone Order Compare screen was not built (that is 7C).

The login button that said "Send reset link" now says "Send reset code".

## 4. Tests

| Suite | Command | Result |
|---|---|---|
| Desktop | `node --test src/*.test.js src/state/*.test.js` | **61 passed** |
| Backend | `pytest tests/` | **492 passed, 0 failed** (unchanged code; 26 pre-existing warnings) |
| Bundle | `esbuild src/App.jsx --bundle` | Completed. No missing reference. |

## 5. Live check

Isolated Vite on `127.0.0.1:5191`, Electron with a fresh profile and CDP port 9339. Dev auto-login stayed on "Signing in…" for the whole check. A direct request to `http://127.0.0.1:8000/docs` timed out, so the shared API did not answer.

While that splash was up, the Stock menu was opened over CDP. Its items were Dashboard and Stock Enquiry. The visible menu text did not contain Stock Availability, Network Stock, Stock (Vertical), or Order Workspace.

The Stock Enquiry body, the Batch / MRP tab, and the Open Procurement button were not clicked, because the screen never left the sign-in splash.

## 6. Left untouched

Quick Stock, `backend/modules/legacy_order/order_process.py`, `backend/tests/test_legacy_order_warehouse_stock_sync.py`, and `backend/storage/whatsapp/send_log.json`.

7C onward was not started.

## FINAL VERDICT

**PARTIAL.** The three screens are removed from the nav and from the render tree, and the Batch/MRP search is in the Stock Enquiry code. The live session confirmed the menu. It did not reach the new search tab or Procurement, because sign-in never finished.
