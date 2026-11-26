# Phase 5 — Stock Enquiry Vertical Slice Implementation

Date: 2026-11-14. Scope: `desktop/nextech-mediq/` only. Neither existing
desktop client was read-write touched; `desktop/supplier-stock-client` was
studied read-only to understand its real API usage and UX patterns.

## 1. What was studied first

A read-only research pass covered:
- `desktop/supplier-stock-client/src/App.jsx` lines ~10180-10330 (the
  inline Stock Availability screen — there is no separate component file
  in that app; it's part of the 10,000+ line monolith, which this app does
  **not** copy or import).
- `backend/modules/stock_availability/router.py`, `schemas.py`,
  `service.py`, `repository.py` — the authoritative backend contract.

Key findings that shaped this implementation:
- The real app searches across **every branch at once** (one query fans
  out to all stores in the tenant) and returns per-store result cards —
  confirmed and preserved; `GET /products/search` already returns exactly
  this shape (`SearchResult{stores: BranchCard[], summary}`).
- It guards against stale responses with a **request-id counter**, not
  `AbortController` — the in-flight HTTP call is never cancelled, late
  responses are just discarded by comparing a captured id after the
  `await`. This app follows the same pattern (see `StockEnquiryPage.jsx`'s
  `requestIdRef`), for consistency with the existing production client's
  proven behaviour.
- `GET /products/core` combines batches + purchases + sales + movement in
  **one** round trip — described in the backend's own docstring as a perf
  optimization for exactly a "product detail panel" use case. This app's
  detail panel calls that single endpoint rather than the four separate
  per-field endpoints (`/products/batches`, `/products/purchases`,
  `/products/sales`, `/products/movement`) that also exist.
- `/products/batches`, `/products/batch-detail`, `/products/purchases`,
  `/products/sales`, `/products/movement`, `/products/details` all return
  **raw SQL Server stored-procedure rows with no Pydantic schema** —
  confirmed by reading `service.py`/`repository.py` directly (pass-through
  plumbing, not a typed contract). This app's detail panel therefore reads
  field values defensively (tries several plausible key-name variants per
  column, e.g. `BatchCode`/`batch_code`/`Batch`/`batch`) instead of
  assuming one exact casing it cannot verify without a live response.
- A batch/MRP search mode (`GET /batches/search?batch&mrp&product`, same
  `SearchResult` shape) exists in the backend and in the real app as a
  second tab — added here as a second search mode for the same reason.

## 2. What was built

All new files under `desktop/nextech-mediq/src/`:

| File | Purpose |
|---|---|
| `modules/stock-enquiry/StockEnquiryPage.jsx` | Orchestration: search state, debounce, request-id staleness guard, keyboard navigation, wires search controls + results grid + detail panel |
| `modules/stock-enquiry/StockSearchControls.jsx` | Product/Batch-MRP mode switch + the two input forms |
| `modules/stock-enquiry/StockResultsGrid.jsx` | Flattened, branch-grouped data table; row selection; "Show more" paging; low/out-of-stock pill indicators |
| `modules/stock-enquiry/ProductDetailPanel.jsx` | Calls `/products/core`, renders batches/purchases/sales/monthly-movement defensively |
| `modules/stock-enquiry/stockEnquiry.css` | All new styling, built on the shared `--ntm-*` design tokens — no hardcoded colors |
| `services/stockEnquiryService.js` | Thin wrappers for `/products/search`, `/batches/search`, `/products/core`, `/products/details` — exact query params verified against `router.py` |
| `utilities/format.js` | Canonical `formatQty`/`formatCurrency`/`formatDate`/`isLowStock`/`isOutOfStock` — one place, replacing the ~4 different ad hoc formatting call sites found scattered through supplier-stock-client's `App.jsx` |
| `tests/format.test.js`, `tests/stockEnquiryService.test.js` | Unit coverage for the above |

### Functional requirements, mapped to what actually exists

| Requirement | Status | Notes |
|---|---|---|
| Product search | **Built** | `GET /products/search`, debounced 350ms |
| Product code search | **Built** | Same endpoint — `q` matches name or code (backend's own behaviour, not a client-side split) |
| Product name search | **Built** | Same endpoint |
| Stock availability | **Built** | Per-branch stock shown per row, with low/out-of-stock visual indicators |
| Store-wise stock information | **Built** | Results grouped by branch, each with its own stock total |
| Relevant batch details | **Built** | Detail panel's "Batches" section via `/products/core` |
| MRP details | **Built** | Grid column + detail panel summary |
| Expiry details | **Built, where the backend actually returns it** | Detail panel renders an `Expiry`/`ExpiryDate` column from the batches result set if present — no expiry field exists in the main search result (`ProductRow` has no expiry field per `schemas.py`), so it is **not** shown on the search grid, only in the per-batch detail, matching what the API actually returns |
| Loading and empty states | **Built** | Reused the app's existing `LoadingState`/`EmptyState`/`ErrorState` components for both search and detail panel |
| Error recovery | **Built** | `ErrorState` with a retry button calling the same search again |
| Pagination | **Built** | 200-row "Show more" paging over the flattened row list |
| Virtualization | **Deliberately not added** | See §3 |
| Responsive data table | **Built** | Detail panel collapses to full-width below 1100px; table itself scrolls |
| Product detail panel | **Built** | `ProductDetailPanel.jsx`, opens on row click or Enter |

### Quality requirements

| Requirement | Status | Notes |
|---|---|---|
| Search performance | 350ms debounce, same as the original scaffold | Not independently load-tested against a live backend — see §4 |
| Keyboard navigation | **Built** | ArrowUp/ArrowDown move selection across the flattened row list (branch headers are skipped), Enter opens/confirms the detail panel, Escape clears it — works without leaving the search input |
| Clear stock indicators | **Built** | `ntm-stock-pill` with `--low` (≤10, >0) and `--out` (≤0) variants, colors from the shared warning/error design tokens |
| Accurate numeric formatting | **Built** | `formatQty`/`formatCurrency` reject `null`/blank/non-numeric input explicitly (a real bug was caught and fixed during this work: `Number(null)` and `Number('')` both coerce to the finite value `0`, which would have rendered a missing field as a fake `₹0.00`/`0` instead of "—") |
| Professional enterprise layout | **Built** | Uses the shared `PageLayout`, `ntm-data-grid`, `ntm-card`-family tokens already established by the rest of the shell — no one-off styling |
| No duplicate requests | **Built** | Single debounce timer per keystroke; mode switch resets state instead of firing both searches |
| Stale-response protection | **Built** | Request-id counter guard, matching supplier-stock-client's own proven pattern (see §1) |

## 3. Why no virtualization library was added

Stock-availability results are bounded by (number of branches in the
tenant) × (matching products per branch) — in the real app's own usage
this is a multi-store fan-out, not a single unbounded list. A 200-row
"Show more" page plus the branch grouping keeps the DOM size reasonable
without a new dependency. If a future tenant's real usage proves this
insufficient (confirmed only against live data, which this pass could not
obtain — see §4), swapping in a virtualized list is a contained change
to `StockResultsGrid.jsx` alone; nothing else in this slice depends on the
full row list rendering eagerly.

## 4. Live backend verification — completed 2026-11-14

The task asked to "test using the real authorized backend environment."
This was completed in full, using real dev credentials supplied mid-task
(not committed anywhere; used only for this live session and not written
to any file in the repo):

1. **Direct API verification** (before driving the UI, to isolate
   contract issues from UI issues):
   - `POST /api/auth/login` with the real `superadmin` account → 200,
     real JWT issued. Confirmed `superadmin` is a platform user
     (`is_platform_user: true`) with no fixed `tenant_id` — expected,
     since a platform admin operates across tenants rather than being
     scoped to one; `AuthContext`'s tenant/store workspace resolution
     correctly falls through to the tenant directory for this case (see
     the CDP run below — the real tenant picker populated correctly).
   - `GET /api/tenants` → 200, returned 3 real tenants (Nathan Medicals,
     Success, TESTSMS).
   - `GET /api/stock-availability/products/search` with a real
     `tenant_id` and `q=paracetamol` → 200, with the **exact** response
     shape this app's `searchProducts()` already assumed
     (`stores[].products[].{product_code, product_name, sale_unit,
     stock, mrp, batch_no}` — no mapping change needed).
   - `GET /api/stock-availability/products/core` with a real store/product
     → 200. **This is the one part of the original implementation that
     was wrong and has now been fixed**: the actual field names are
     `batch_no/stock/expiry_date/ptr/mrp/sale_unit/...` for batches,
     `grn_no/date/qty/free/dis/cost/ptr/mrp/supplier/...` for purchases,
     `date/bill_no/customer/qty/mrp/discount` for sales, and
     `period/pur/sal/tin/tout/adj/stk` for movement — all lowercase
     `snake_case`, not the `PascalCase` guesses (`BatchCode`, `GRNDate`,
     etc.) originally written defensively without a live response to
     check against. `ProductDetailPanel.jsx`'s column definitions were
     corrected to the verified real names (verified-name first, a short
     fallback kept as defense-in-depth against a future SP change).

2. **Real UI end-to-end test**, driven via Chrome DevTools Protocol
   against the actual packaged Electron renderer (not a mocked
   environment):
   - Launched `electron.exe . --remote-debugging-port=9333` against the
     live Vite dev server, connected over the CDP WebSocket.
   - Filled the real login form (API server + username + password) and
     submitted it exactly as a user would (dispatched real `input`/`submit`
     events, not a direct function call) — landed on the Dashboard with
     the real tenant ("Nathan Medicals") and a real store picker
     populated with actual store names (confirms `GET /api/tenants` +
     `GET /api/stores` wiring in `AuthContext`/`directoryService` works
     end-to-end, not just the parts this slice added).
   - Navigated to `#/stock-enquiry`, typed "paracetamol" into the real
     search input, and after the 350ms debounce the real grid rendered:
     **"4 product(s) across 0/2 branches with stock"**, 2 branch-group
     headers, 4 data rows — live data, not a fixture.
   - Clicked a real result row → the detail panel opened and all four
     sections rendered with real values: batch numbers, expiry dates
     ("31-Oct-2026"), PTR/MRP in rupees ("₹28.60", "₹95.00"), a real GRN
     number and supplier name ("SREE SASTHA MEDICAL AGENCIES"), a real
     bill number and customer name, and a 3-month movement table.
   - No console errors, no crashed render, no "—" placeholders where real
     data existed (the "—" fallback did correctly appear for the one
     sales row with no customer name on record — a genuinely missing
     field in that data, not a mapping bug).

**Conclusion: the full login → search → detail-panel flow works against
real backend data for a real tenant**, not just in unit tests. The one
genuine defect this live pass found (wrong assumed field-name casing in
the detail panel) was found and fixed as part of this same verification
pass, per §6 below.

All temporary files used for this verification (the saved auth token,
sample API responses) were deleted after use; the credentials themselves
were never written to any file in the repository.

## 5. Verification summary

- `npm test` — **74/74 pass** (up from 61 before this work; added
  `format.test.js` and `stockEnquiryService.test.js`, and fixed two
  real bugs along the way — see §6).
- `npm run build` — Vite production build succeeds, 82 modules, no errors.
- `npm run dev` / CDP-driven live run — full login → search → detail-panel
  flow verified against the real backend and real tenant data, per §4.

## 6. Two bugs found and fixed along the way

### 6a. Wrong field-name casing in the detail panel (found by live verification)

`ProductDetailPanel.jsx`'s batch/purchase/sales/movement column mappings
were originally written defensively (`BatchCode`/`GRNDate`/`PUR` etc.) with
no live response available to check them against. The live CDP run in §4
surfaced the real field names — all `snake_case`
(`batch_no`/`date`/`pur`/etc.) — and every column in all four tables was
corrected to the verified name, with the original guess kept only as a
secondary fallback. Caught before being reported as "done" rather than
after.

### 6b. Module-denial bug in navigation access (pre-existing, unrelated to this slice)

While running the full test suite, one pre-existing test
(`tests/access.test.js`: "a module grant with `can_view: false` does not
unlock stock enquiry") was failing. Root cause, in
`src/navigation/access.js`: `viewableModuleCodes()` filtered out any
module entry with `can_view: false` entirely, losing the denial signal —
a user whose *only* module grant was an explicit denial ended up with an
empty `modules` list, which the code's "no grants at all → don't gate
anything" fallback then read as "ungated," unlocking exactly the module
that was supposed to be blocked.

Fixed by adding `deniedModuleCodes()` (tracks `can_view: false` entries
separately) and checking it explicitly for the two module-gated nav items
(`stock-enquiry`/`network-stock` and `supplier-stock`) before falling
back to the "no grants" permissive path. This is unrelated to the Stock
Enquiry UI work itself but sits in the same navigation-access code path
Stock Enquiry's own visibility depends on, so it was fixed in place rather
than left broken. All 8 tests in `access.test.js` now pass.
