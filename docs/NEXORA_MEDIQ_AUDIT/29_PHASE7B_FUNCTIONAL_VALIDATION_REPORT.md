# 29 — Phase 7B.1 functional validation
**NEXORA MEDIQ — closure check for commit `ac92f01`**
Date: 2026-11-13

This file is the validation report. It does not replace `29_PHASE7_FORGOT_PASSWORD_SMTP.md`.

## 1. Git baseline

- Branch: `nexora-mediq-implementation`
- HEAD: `ac92f01` (`feat(desktop): keep Stock Enquiry and Procurement as the single screens`)
- Docs read before testing: `30_PHASE7A_FRONTEND_GAP_INVENTORY.md`, `31_PHASE7B_COLLAPSE_DUPLICATE_SCREENS.md`
- No existing commit was rewritten.

Unrelated dirty files were left untouched, including Quick Stock, `backend/modules/legacy_order/`, `backend/modules/procurement/decision_repository.py`, `workspace_repository.py`, untracked `product_identity.py`, and `backend/storage/whatsapp/send_log.json`.

The live Electron process loaded two extra uncommitted edits that are not in `ac92f01`:

- `package.json` version `0.1.71` → `0.1.72` (the window title showed v0.1.72)
- `ProcurementWorkspace.jsx` now passes rows through `pwCollapseRows` from an uncommitted `procurementWorkspaceView.js`

## 2. Why port 8000 was down, and how it was started

At the start of this check, `Get-NetTCPConnection -LocalPort 8000 -State Listen` returned no listener. The earlier "Signing in…" hang was a client waiting on a port with no API process.

`backend/.env` points at `DB_SERVER=192.168.10.73`, `DB_DATABASE=NEXORA_PLATFORM`. That is the development server named in `backend/config/database.py`. It is not the production host `.32`. No production configuration was edited.

Startup command, bound to loopback only:

`E:\Nexora\backend\.venv\Scripts\python.exe -m uvicorn api.app:app --host 127.0.0.1 --port 8000`

The process logged `Application startup complete` and `GET /docs` returned 200. The process was left running because other local clients began calling it immediately.

## 3. Stock Enquiry

Isolated Vite on `127.0.0.1:5192` (`VITE_DEV_SCREEN=stock_vertical`, API base `http://127.0.0.1:8000`) and Electron with a fresh profile and CDP port 9341. Dev auto-login completed as `devadmin` / `SUPER_ADMIN`.

Observed:

- The heading was **Stock Enquiry**.
- Tabs **Product** and **Batch / MRP** were present.
- The Inventory section listed Stock Enquiry, Non-Moving Stock, and NMW Sales Report.
- The visible navigation text did not contain Stock Availability, Network Stock, Stock (Vertical), or Order Workspace.
- Product search `para` called `GET /api/stock-availability/products/search?...&q=para&only_stock=0` and the status line became `120 match(es) across 6 store(s).` Store columns rendered for NMW, NMC, NMG, NMS, NMV, and NMA, and product-core requests returned 200.

## 4. Batch / MRP search

The Batch / MRP tab showed inputs Batch number, MRP, and Product name. A search issued:

`GET /api/stock-availability/batches/search?...&batch=NO-SUCH-BATCH-7B1`

The API answered **200**. The status line was still `Searching batches…` at the 2.5s sample. Before a later sample, further batch requests ran (`batch=3`, `batch=37`, `batch=375`). The status line then read `104 match(es) across 6 store(s).`, and product-core calls for those results returned 200. So a real batch prefix rendered. The empty-result sentence for `NO-SUCH-BATCH-7B1` was not the text on screen when it was read back.

A transport-error state was not induced. The code path in `StockVerticalView` returns the request error for a failed batch search and does not fall back to the offline name index. That branch was not executed live.

## 5. Procurement Workspace

The Procurement submenu item opened a screen whose heading is **Procurement**. The active nav label was Procurement. The API log for that open included `GET /api/procurement/export-defaults` **200** and `GET /api/legacy-order/stores?active_only=true` **200**, plus the NMW workflow, header, suppliers, and qty-check calls, all **200**.

No quantity was edited and no order was finalized or submitted.

The live component includes the uncommitted `pwCollapseRows` change noted in §1. The heading and the initial API calls are the committed screen plus that row-collapse wrapper.

## 6. Order Entry

Order Entry opened. Headings included Order Entry, Current order, New order, and Received, not ordered by the app. The body said **No order yet.** The form shows Last bill, Last GRN, order type Regular / WH, and Sync & Generate Order. `GET /api/legacy-order/orders/NMW/order-entry` and the received-not-ordered call were issued.

`state.blocked` was false, so the **Open Procurement** button was not in the DOM. The source in `PmOrderEntry.jsx` still renders that label only inside the blocked-order branch, and `App.jsx` passes `onOpenWorkspace` as `setActiveScreen('procurement_workspace')`. The click was not performed. Generating an order to force the blocked branch was not done.

The live session was a super-admin login. The purchase-manager / salesman nav filters in `App.jsx` were not re-executed under those roles. The filter expressions no longer mention `order_workspace`; they still hide Procurement, Rate Analysis, and Order Entry unless the session is a super admin or `canViewPurchaseDetails`.

## 7. Removed-screen verification

Searched `desktop/supplier-stock-client/src` for screen ids `stock`, `network_stock`, and `order_workspace`, and for `from './OrderWorkspace'`. No matches.

`erpNav.js` inventory screens are `stock_vertical`, `non_moving`, `nmw_sales`. Procurement screens are `procurement_workspace`, `order_entry`, `legacy_order`, `analysis`, `rate_analysis`.

`OrderWorkspace.jsx` is deleted in `ac92f01`. Shared modules still imported by Procurement were not deleted: `OwSharedControls.jsx`, `OwFormatters.js`, `OwDocumentCard.jsx`, `OwIntelligencePanel.jsx`, `OwExportKit.js`.

Comments in `App.jsx` still say "Stock Availability" and "OrderWorkspace.jsx". Those are comments, not routes. `network_stock_qty` remains a supplier-analysis field name, not a screen.

## 8. Login and password reset

The forgot-password submit control in `App.jsx` is the text **Send reset code**. Dev auto-login replaced the login form, so that button was not on screen during this session.

The workflow behind it is real, not a renamed stub:

- `backend/modules/password_reset/service.py` issues a hashed single-use token, 30-minute expiry, a 3-per-hour limit, and a generic response.
- `pytest tests/test_password_reset.py` — exit 0, **25 passed**.
- `send_reset_email()` sends over STARTTLS only when `NEXORA_PASSWORD_RESET_SMTP_HOST`, `_USERNAME`, and the password variable are set. Otherwise it returns false and does not claim a send. No mailbox was configured in this check, and no message was sent.

## 9. Tests and build

| Command | Where | Exit | Result |
|---|---|---|---|
| `node --test src/*.test.js src/state/*.test.js` | `desktop/supplier-stock-client` | 0 | **65 passed, 0 failed**. Four of those are uncommitted procurement-identity cases. The committed 7B tree's suite was 61. |
| `pytest tests/` | `backend`, `.venv` | 0 | **492 passed, 0 failed**, 26 pre-existing warnings |
| `pytest tests/test_password_reset.py` | `backend` | 0 | **25 passed** |
| `npx vite build` | `desktop/supplier-stock-client` | 0 | 118 modules, built in 2.89s |

There is no component test that mounts Stock Enquiry or the sidebar. The desktop suite does not render those screens. The live CDP session above is the check for them.

## 10. Outstanding

- The nonsense batch search returned HTTP 200, and the on-screen empty sentence was not captured before a later batch query replaced the status line.
- A failed batch request (network or HTTP error) was not provoked.
- Open Procurement was not clicked, because the signed-in store had no blocked prior-day order.
- Non-admin nav hiding was not logged in live.
- SMTP delivery of a reset code was not executed.
- Network Stock CSS (`.network-stock-screen`) is still in `styles.css` and unused except the tab classes Stock Enquiry reuses.

## FINAL VERDICT

**PARTIAL.** Stock Enquiry, the Batch/MRP request, Procurement's open, and Order Entry's open were exercised against the local API. The blocked-order button click and the batch empty/error sentences were not confirmed on screen.

Phase 7C was not started.

## 11. Dark mode UI modernization

Dark is the primary theme. The work is token-based in `desktop/supplier-stock-client` and does not change business logic, API contracts, or authorization.

### Behavior

- A new installation with no saved `themePreference` defaults to dark. A value already stored as `light`, `dark`, or `system` is left as saved.
- The menubar and Settings → Appearance both offer Dark, Light, and System. The choice is written to `nexora.desktop.settings` and applied on `documentElement` immediately, without a reload.
- System follows `prefers-color-scheme`. `theme.test.js` covers the resolver. The operating-system theme was not flipped during the live pass.
- Light mode keeps a dark brand menubar and a light canvas, sidebar, cards, and grids.

### Tokens

Dark surfaces are `#0B1220` (canvas), `#111827` (sidebar and menubar), `#1E293B` (cards), `#263449` (raised headers), and `#334155` (borders). Text is `#F8FAFC` / `#CBD5E1` / `#94A3B8`. The accent is `#14B8A6`, with dark ink on that fill so button labels stay readable. Success, warning, and error use the requested hues. Light mode uses the darker teal `#0F766E` for filled controls so white labels still meet contrast.

### Screens inspected

Rendered in the Vite app at `127.0.0.1:5193` after dev login, in dark and then light. Navigation confirmed the active item for each of these:

Dashboard, User Management, Role Management, Procurement, Order Entry, Legacy Order, Supplier Stock Analysis, Rate Analysis, Stock Enquiry (Product and Batch / MRP), Non-Moving Stock, NMW Sales Report, Time Report (the Sales & Reports item), Sync Live, Label Exporter, Schema Sync, and Settings.

WhatsApp is a real screen, but this login did not show it because `storeWhatsAppAvailable()` was false. Its chrome was not opened.

Screenshots of the rendered dark theme: Dashboard, Stock Enquiry, Batch / MRP, Procurement, Settings, Rate Analysis. Light theme: Settings, Procurement, Stock Enquiry. Switching Settings from Dark to Light updated the whole window immediately, and the saved preference read back as `light`, then was set back to `dark`.

### Defects fixed in this pass

- The old dark palette was a near-black blue. It now uses the slate tokens above, including sidebar, cards, inputs, grid headers, scrollbars, and the modal overlay.
- Filled accent buttons used white text on `#14B8A6`, which is too light. Those labels use `--nx-accent-on`.
- Stock Enquiry's active Product / Batch tab and the stock workbench accent were still the old blue. They follow the theme accent.
- The quote box on Rate Analysis was a browser-default grey textarea. `textarea` now uses the same surface, text, and border as other fields.
- Sync Live status badges used fixed green, red, and amber that ignored the theme.

### Tests and build

| Command | Where | Exit | Result |
|---|---|---|---|
| `node --test` on `src/*.test.js` and `src/state/*.test.js` | `desktop/supplier-stock-client` | 0 | **68 passed, 0 failed** (the previous 65, plus 3 theme tests) |
| `pytest tests/` | `backend` | 0 | **492 passed, 0 failed**, 26 pre-existing warnings |
| `npx vite build` | `desktop/supplier-stock-client` | 0 | 118 modules. Re-run after the textarea rule. |

### Remaining visual issues

- Individual modal, popover, and tooltip instances were not each opened. Shared dialog rules use the overlay and surface tokens.
- Procurement chart labels stay small. Row density, column widths, and scrolling were not changed.
- Unused Network Stock CSS is still in `styles.css`.
- A few semantic fills (store column bands, offer badges, label-review chips) stay on their own colors so their meaning does not collapse into the accent.

The Phase 7B.1 verdict above is unchanged: **PARTIAL**. This section does not start Phase 7C.

