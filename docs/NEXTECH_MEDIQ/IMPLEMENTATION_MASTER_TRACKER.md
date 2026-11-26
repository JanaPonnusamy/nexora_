# NexTech MediQ Workspace — Implementation Master Tracker

**Read this file first in any new session (Claude, Cursor, or otherwise)
before touching `desktop/nextech-mediq/`.** It is the single source of
truth for what has been built, what decisions have been locked in, and
what remains. Update it at every phase boundary — do not let it go stale.

Product: **NexTech MediQ Workspace** — *Intelligent Pharmaceutical
Workspace* (renamed 2026-11-14 from "NexTech MediQ" — see "Product rename"
section below; the folder path `desktop/nextech-mediq/` was deliberately
**not** renamed)
Repository path: `E:\Nexora\desktop\nextech-mediq` (new, independent
Electron app, sibling to the two existing clients)
Reference docs: `docs/NEXTECH_MEDIQ/01_PHASE1_ARCHITECTURE_DISCOVERY.md`
(architecture discovery, already complete),
`docs/NEXTECH_MEDIQ/EXISTING_CLIENT_SEPARATION_FINAL_REPORT.md` (verified
zero code-level coupling between all three desktop apps, 2026-11-14)

---

## Locked architectural decisions (do not re-litigate these)

| # | Decision | Value |
|---|---|---|
| 1 | Relationship to existing apps | NexTech MediQ is a **third, independent** Electron app. `desktop/supplier-stock-client` and `desktop/quick-stock-client` are **never modified** — reference/inspiration only, never imported at runtime. |
| 2 | Application identity | `appId: com.nextech.mediq.workspace`, `productName: "NexTech MediQ Workspace"`. **Renamed 2026-11-14** from the original `com.nextech.mediq.desktop` / `"NexTech MediQ"` — see "Product rename" section below for why. Distinct from supplier-stock-client's own in-progress, independently-sanctioned rebrand to `"NexTech MediQ"` (commit `960b3a5` + `docs/NEXORA_MEDIQ_AUDIT/24_PHASE5_REBRANDING_AND_WATCHDOG_REPORT.md`) and quick-stock-client's `"NexTech Quick Stock"` — neither of those existing values is touched. |
| 3 | Windows/Electron version floor | **Electron 22.3.27, pinned** — matches both existing clients, for Windows 7/8 fleet compatibility (owner override of the spec's own Win10/11-only suggestion — confirmed explicitly by the owner). |
| 4 | First functional module | Stock Enquiry / Stock Lookup (built — see Phase 5 below). |
| 5 | Repo placement | New folder inside the same repo: `desktop/nextech-mediq/`, not a separate git repository. |
| 6 | Router | `react-router-dom`, `HashRouter` (not `BrowserRouter` — this app loads via `file://` in production, which `HashRouter` handles correctly without OS history API support). |
| 7 | Backend contracts used | Only existing, unmodified endpoints. No new backend endpoint has been created by this work. See "API contracts in use" below. |

## Product rename — 2026-11-14: "NexTech MediQ" → "NexTech MediQ Workspace"

`docs/NEXTECH_MEDIQ/EXISTING_CLIENT_SEPARATION_FINAL_REPORT.md` found that
`desktop/supplier-stock-client` is **independently, deliberately** mid-rebrand
to "NexTech MediQ" (its own commit `960b3a5`, documented in
`docs/NEXORA_MEDIQ_AUDIT/24_PHASE5_REBRANDING_AND_WATCHDOG_REPORT.md`) — this
was pre-existing, sanctioned work, not contamination from this project. That
left two apps both displaying as "NexTech MediQ" (distinct `appId`s, so no
technical/install collision, but identical Start Menu entries). The owner
decided: **this new app renames, supplier-stock-client's rebrand stands.**
New name: **NexTech MediQ Workspace**.

Files changed for the rename (all inside `desktop/nextech-mediq/`, folder
path itself left as `nextech-mediq` — only user-visible identity strings
changed):

- `package.json` — `appId` → `com.nextech.mediq.workspace`, `productName` →
  `"NexTech MediQ Workspace"`, `description`, and the `dist` script's
  installer artifact name (`NexTechMediQWorkspace-Setup-...`).
- `index.html` — `<title>` → `NexTech MediQ Workspace` (Electron's window
  title follows this; no separate title is set in `electron/main/index.cjs`).
- `src/components/BrandLockup.jsx` — `alt` text updated.
- `src/themes/tokens.js` — `BRAND.name` updated.
- `src/components/ErrorBoundary.jsx`, `src/modules/dashboard/DashboardPage.jsx`
  — in-app copy/log-prefix strings updated.
- `src/assets/branding/svg/nextech-mediq-standard.svg` and
  `nextech-mediq-standard-dark.svg` — the visible lockup artwork itself.
  The main title text was **not** grown to fit "Workspace" inline (would
  have risked overflowing the 1100×190 viewBox); instead a small
  "WORKSPACE" pill badge was added beneath the tagline, in the exact visual
  pattern the brand pack's own `nextech-mediq-ai-powered.svg` variant
  already uses for its "AI POWERED" badge (same badge shape/position,
  theme-appropriate colors for each variant). `<title>` tags in both SVGs
  updated to match.
- **Not changed**: `nextech-mediq-ai-powered.svg`, `nextech-mediq-ai-powered-dark.svg`,
  `nextech-mediq-app-icon.svg`, `icon.ico`, any PNG exports, or the
  `branding/README.md` — only the two "standard" lockup SVGs actually
  rendered by `BrandLockup.jsx` were touched. If the AI-powered variant or
  app-icon mark are ever wired into the UI, they'll need the same
  "Workspace" treatment applied separately.

Verified after the rename: `npm run build` (63 modules, exit 0), `npm test`
(22/22 pass), and a live `npm run dev` launch — Electron's
`MainWindowTitle` confirmed as **"NexTech MediQ Workspace"** via
`Get-Process`.

**Not yet updated** (flagged, not done, since they're outside
`desktop/nextech-mediq/`'s own files and weren't part of this specific
rename task): `CURSOR_HANDOFF_MASTER_PROMPT.md` and this tracker's own
earlier prose still say "NexTech MediQ" in some narrative sections written
before the rename — read those sections as historical record of what was
true when written, not as contradicting the rename decision recorded here.

## Phase status

| Phase | Status | Notes |
|---|---|---|
| 1 — Architecture Discovery | **COMPLETE** | `docs/NEXTECH_MEDIQ/01_PHASE1_ARCHITECTURE_DISCOVERY.md` |
| 2 — New Project Foundation | **COMPLETE** | Electron main/preload/IPC, Vite+React, build+dev scripts, foundation tests all pass, production build verified, dev-mode launch verified (Electron window titled "NexTech MediQ" confirmed rendering) |
| 3 — Unified Shell & Design System | **COMPLETE** (premium shell, 2026-11-14) | Grouped sidebar, breadcrumbs, Ctrl+K search, notifications, user menu, tenant/store chip, theme selector, page layout, planned-module pages. Honest status flags unchanged: only Dashboard, Stock Enquiry, Settings are enabled. Documented in `docs/NEXTECH_MEDIQ/03_PREMIUM_UI_IMPLEMENTATION.md`. |
| 4 — Authentication & API Integration | **COMPLETE** (client + live login, 2026-11-14) | Login, logout, session restore, JWT expiry, 401 handling, tenant/store selection, and permission-aware nav. Live `POST /api/auth/login` against `http://127.0.0.1:8000` returned **HTTP 200** and a token (token not recorded). See `docs/NEXTECH_MEDIQ/04_AUTH_TENANT_INTEGRATION.md`. The 2026-11-13 HTTP 500 attempt is kept below as history. |
| 5 — Stock Enquiry Vertical Slice | **COMPLETE** (full live UI verification, 2026-11-14) | Product search + batch/MRP search modes, keyboard navigation, branch-grouped results grid with stock-level pills, and a product detail panel (batches/purchases/sales/monthly-movement via `/products/core`) — all built and then driven end-to-end through the real Electron UI via CDP against a real tenant ("Nathan Medicals") with real data. One real bug found and fixed during this verification: the detail panel's column field-name guesses (`BatchCode`, `GRNDate`, etc.) were wrong — the real API returns `snake_case` (`batch_no`, `date`, `pur`, etc.); corrected against a live response. See `docs/NEXTECH_MEDIQ/05_STOCK_ENQUIRY_IMPLEMENTATION.md`. |
| 6 — Supplier Stock Integration | **PARTIAL** | Read-only supplier list and product search are in the shell and were called live. Excel import, mapping writes, and assignment saves are not wired. See `06_COMPLETE_WORKSPACE_INTEGRATION.md`. |
| 7 — Quick Stock Integration | **PARTIAL** | The kiosk routes were called live with the passcode header. The Electron page was not driven. The passcode is not stored and is not shown. |
| 8 — Procurement / Legacy Order Architecture | **PARTIAL** | Cycle list, rules catalog, legacy health, branch list, order grid, and order-entry readiness are read-only. No cycle is opened and no order is submitted. Owner decisions in `13_UNKNOWNS_AND_OWNER_DECISIONS.md` still block the write workflows. |
| 9 — Additional Inventory/Intelligence | **PARTIAL** | Non-moving report, network store list, stock check sublocations, stock integrity, product-mapping search, expiry store summary, sale-analysis search, and time-report metadata were called live. NMW bills did not return within 40 seconds. Shelf-sort classify was not called again. |
| 10 — Administration & Settings | **PARTIAL** | User list is live. Settings no longer edits an API host. Role creation and permission edits are not wired. |
| 11 — Quality/Performance/Accessibility | **NOT STARTED** | Rate analysis at 90 days and the non-moving dashboard were too slow for a short timeout. The rate screen now asks for 30 days, which did return. |
| 12 — Security Validation | **PARTIAL** | Token is no longer written to `localStorage`. Electron `safeStorage` holds the remembered copy. The renderer still keeps the token in memory so `fetch` can send it. Logout still does not revoke a platform-user JWT. |
| 13 — Testing & Full Regression | **PARTIAL** | `npm test` 79/79, exit 0, on 2026-11-14 after this integration. Live HTTP and one Electron CDP pass are recorded in `06_COMPLETE_WORKSPACE_INTEGRATION.md`. Not every screen was clicked in Electron. |
| 14 — Packaging & Installer Readiness | **PARTIAL** | Unsigned NSIS installer built. First `npm run dist` exited 1 because winCodeSign could not create symlinks. Retry with `signAndEditExecutable=false` exited 0. Not signed and not published. |
| 15 — Final Release Readiness | **NOT STARTED** | |

## What actually works right now (verified, not assumed)

- `npm install` succeeds (390+ packages, Electron 22.3.27).
- `npm test` — **74/74 tests pass** (re-run 2026-11-14 after Phase 5, exit code 0).
- `npm run build` — Vite production build succeeds (exit code 0; 82 modules; `dist/assets/index-C_XfO3e1.js` 229.70 kB, gzip 73.51 kB).
- **Full Stock Enquiry flow verified live, through the actual Electron UI**, via a real dev account (2026-11-14): login → real tenant/store picker populated from live `GET /api/tenants`/`GET /api/stores` → product search returning real multi-branch results → clicking a result row opened the detail panel with real batch/purchase/sales/monthly-movement data rendered correctly (currency, dates, quantities all formatted as expected). See the milestone section below for the full transcript.
- Live login against `http://127.0.0.1:8000/api/auth/login` returned **HTTP 200** and a token field (2026-11-14). The token is not recorded. Invalid password returned **401**. An expired JWT returned **401** with detail class `token-expired`. `POST /api/auth/logout` returned **200**.
- `GET /api/tenants` returned **200** (3 tenants) and `GET /api/stores` returned **200** (10 stores) for that platform-user session. `GET /api/stores/tenant/{id}` returned **200** for each of the three tenants. The dev account's user has no `tenant_id`, so the tenant chip is required.
- `npm run dev` — **verified end-to-end**: Vite dev server starts, Electron launches, main window renders with title "NexTech MediQ", IPC bridge (`window.nextechMediq`) connects, theme/health-check IPC round-trips work.
- Login screen renders when unauthenticated (confirmed again on 2026-11-13 via CDP: document title `NexTech MediQ`, no shell heading until auth).
- A local Nexora API is reachable at `http://127.0.0.1:8000` (this machine is `192.168.10.80`, same process also accepts `http://192.168.10.80:8000`). `GET /openapi.json` returned 200, title `NEXORA API`, and includes `POST /api/auth/login` and `GET /api/stock-availability/products/search`. The process was already listening (PID 14776, system Python 3.12). It was started from `E:\Nexora\backend` with the project venv command `python -m uvicorn api.app:app --host 0.0.0.0 --port 8000`. It was not killed and not replaced.
- That API's `backend/.env` database target was checked without printing secrets: `DB_SERVER` is the dev host `192.168.10.73`, `DB_DATABASE` is `NEXORA_PLATFORM`, and it is not `192.168.10.32`. The shell environment matched that same dev host. No connection was made to `192.168.10.32`.

## What has NOT been verified yet (be honest about this)

- The Phase 4 login/tenant/store controls and the Phase 5 Stock Enquiry flow ARE now verified inside a real Electron window via CDP (2026-11-14, see milestone below) — the line below from the earlier Phase 4 pass is kept as history, not current status.
- ~~The Phase 4 login, tenant, and store controls were not clicked inside an Electron window. Live checks were HTTP calls. The last Electron launch recorded above is still the earlier shell launch.~~ (superseded, see above)
- Non-platform accounts (stock viewer, purchase manager, salesman) were not signed in. Their nav gates are unit-tested with mocked users only.
- No cross-tenant stock request was sent as a non-platform user. The platform dev account was allowed to read all three tenants, which matches the server's unrestricted scope for that role. `assert_tenant_access` was not probed with a restricted account.
- `POST /api/auth/logout` returned 200 for the platform user, and the same bearer still received `GET /api/tenants` **200**. Full-access tokens have no session id, so logout does not revoke the JWT. The client clears its local copy.
- An unsigned installer was produced on 2026-11-14: `desktop/nextech-mediq/release/NexTechMediQWorkspace-Setup-0.1.0.exe`. It is not signed and was not published. The first packaging attempt exited 1 (winCodeSign symlink privilege). The retry exited 0.
- **No accessibility/keyboard-navigation audit.**
- **No test against Windows 7/8** specifically (Electron 22 is pinned for that reason, but the actual OS target has not been exercised).
- Dev SQL `192.168.10.73:1433` accepted TCP on 2026-11-14. Port **1434** still did not. The 2026-11-13 timeouts below are historical.

## Live backend milestone (2026-11-13) — attempted, not passed

This is the first next step from `CURSOR_HANDOFF_MASTER_PROMPT.md`: run `desktop/nextech-mediq` against a live local backend. Phases 6–15 were not started.

Commands and results, from `E:\Nexora\desktop\nextech-mediq` unless noted:

| Check | Command / probe | Result |
|---|---|---|
| Unit tests | `npm test` | Exit code **0**. 22 passed, 0 failed. |
| Production build | `npm run build` | Exit code **0**. 63 modules. `dist/assets/index-DTP0D9uj.js` 185.11 kB (gzip 60.49 kB). |
| Who owns port 8000 | `netstat` + process command line | PID **14776** listening on `0.0.0.0:8000`. Existing Nexora uvicorn from `E:\Nexora\backend`. Not killed. |
| API identity | `GET http://127.0.0.1:8000/openapi.json` | HTTP 200. Title `NEXORA API`. Login and stock-search routes present. |
| Default API host | `GET http://192.168.10.73:8000/openapi.json` | Failed (`URLError`). That host does not serve the API from this machine. |
| Dev database port | TCP connect to `192.168.10.73:1433` and `:1434` | Both `TimeoutError` (4s). |
| Electron window | Vite on `127.0.0.1:5183`, then `electron.exe --remote-debugging-port=9222` with a fresh user-data dir, `ELECTRON_RUN_AS_NODE` unset | Page title **NexTech MediQ**. CDP `Runtime.evaluate` drove the login form. |

Login, using the existing dev account (credentials not recorded here):

1. Default API server `http://192.168.10.73:8000` — the window showed **Failed to fetch**. No HTTP call reached the local API.
2. API server changed on the login form to `http://127.0.0.1:8000` and saved before submit — the window showed **Request timed out** (client abort at 30s). The API access log then recorded `OPTIONS /api/auth/login` **200** and `POST /api/auth/login` **500**. The 500 matches the API's inability to open its dev SQL connection (`pyodbc` named-pipes error 64, then `pytds` TCP timeout). No `user` and no token came back.
3. Stock Enquiry was not opened. Search URL was not called. Nothing rendered.

Client fix made so a fresh profile can aim at the API that is actually up: `src/app/LoginPage.jsx` now has an **API server** field. Settings used to be the only place to edit `apiBaseUrl`, and Settings is behind `RequireAuth`, so a wrong default could not be corrected before login. The field is written with `saveSettings` before `POST /api/auth/login`. The default remains `http://192.168.10.73:8000`; it was not rewritten to hide the failed default. Electron stayed at 22.3.27. No backend route was added or changed. Neither existing desktop client was modified.

## Live backend milestone (2026-11-14) — login passed

Dev SQL port 1433 was reachable, so the same dev account was tried again from this machine against `http://127.0.0.1:8000`. No credential, token, or `.env` value is written here. Full table: `docs/NEXTECH_MEDIQ/04_AUTH_TENANT_INTEGRATION.md`.

| Check | Result |
|---|---|
| `npm test` | Exit code **0**. 61 passed, 0 failed. |
| `npm run build` | Exit code **0**. 82 modules. JS 229.14 kB (gzip 73.39 kB). |
| TCP `192.168.10.73:1433` / `:1434` | 1433 open. 1434 closed. |
| `POST /api/auth/login` | **HTTP 200**. Token field present. Not recorded. |
| Invalid password | **HTTP 401**. |
| Expired JWT and garbage bearer | **HTTP 401** (`token-expired` and `invalid-token`). |
| Tenant and store directory | **HTTP 200**. 3 tenants, 10 stores. Per-tenant store route 200 for all three. |
| Stock search with the first returned tenant | **HTTP 200**. 6 store cards. Grid not opened in Electron. |
| `POST /api/auth/logout` | **HTTP 200**. The same platform-user bearer still worked afterwards. |

`GET http://192.168.10.73:8000/openapi.json` also returned **200** this run. No credentials were sent to that host. The in-app default URL was left as `http://192.168.10.73:8000`.

## Live backend milestone (2026-11-14, continued) — Phase 5 full UI verification passed

Real dev credentials were supplied for this pass (`superadmin` account).
They were used only in-memory for this verification and never written to
any file in the repository; temp files holding a token/API response were
deleted afterward. Full detail: `docs/NEXTECH_MEDIQ/05_STOCK_ENQUIRY_IMPLEMENTATION.md` §4.

| Check | Result |
|---|---|
| `POST /api/auth/login` (direct API call, to isolate the contract from the UI) | **200**. `superadmin` confirmed as a platform user (`is_platform_user: true`), no fixed `tenant_id` — expected for a cross-tenant admin. |
| `GET /api/tenants` | **200**. 3 real tenants (Nathan Medicals, Success, TESTSMS). |
| `GET /api/stock-availability/products/search?q=paracetamol` with a real tenant_id | **200**. Response shape matched `searchProducts()`'s existing assumptions exactly — no code change needed here. |
| `GET /api/stock-availability/products/core` for a real store+product | **200**. **Field names did NOT match the original defensive guesses** (`BatchCode` etc.) — real shape is `snake_case` (`batch_no`, `expiry_date`, `ptr`, `grn_no`, `pur`/`sal`/`tin`/`tout`/`adj`/`stk`, etc.). `ProductDetailPanel.jsx` was corrected to the verified names. |
| Full UI run via CDP (`electron.exe . --remote-debugging-port=9333`, real `input`/`submit` events, not direct function calls) | Login → landed on Dashboard with a real populated tenant/store picker → navigated to `#/stock-enquiry` → typed "paracetamol" → real grid rendered ("4 product(s) across 0/2 branches with stock", 2 branch headers, 4 rows) → clicked a result row → detail panel opened with real batch/purchase/sales/movement data, correctly formatted (₹ currency, dates, quantities). No console errors. |

This is the first fully-live, UI-level (not just HTTP-level) verification
of any module in this app. The CDP driver script is not part of the repo
(it was a scratchpad throwaway) — if a repeatable E2E harness is wanted
going forward, it should be rebuilt as a proper test file under `tests/`
or a new `e2e/` directory, not re-derived ad hoc each time.

## Files created so far (all under `desktop/nextech-mediq/`, all new — nothing in either existing client was touched)

```
package.json, vite.config.js, index.html
electron/main/index.cjs
electron/preload/index.cjs
electron/ipc/channels.cjs
electron/ipc/registerHandlers.cjs
electron/security/windowDefaults.cjs
scripts/wait-and-launch.mjs
src/app/main.jsx, App.jsx, LoginPage.jsx, RequireAuth.jsx, login.css
src/themes/tokens.js, tokens.css, themeLogic.js, ThemeContext.jsx
src/layouts/AppShell.jsx, Sidebar.jsx, TopBar.jsx, PageLayout.jsx, Breadcrumbs.jsx, GlobalSearch.jsx, NotificationArea.jsx, TenantContext.jsx, UserMenu.jsx, ThemeSelector.jsx, shell.css
src/navigation/navConfig.js
src/ui/icons.jsx
src/modules/planned/PlannedModulePage.jsx
src/contexts/AuthContext.jsx
src/components/BrandLockup.jsx, ErrorBoundary.jsx
src/components/states/LoadingState.jsx, EmptyState.jsx, ErrorState.jsx
src/services/settingsStore.js, sessionStore.js, authService.js, stockEnquiryService.js
src/api/client.js
src/modules/dashboard/DashboardPage.jsx
src/modules/settings/SettingsPage.jsx
src/modules/stock-enquiry/StockEnquiryPage.jsx, StockResultsGrid.jsx, StockSearchControls.jsx, ProductDetailPanel.jsx, stockEnquiry.css
src/utilities/format.js
tests/foundation.test.js, themeLogic.test.js, sessionStore.test.js, settingsStore.test.js, apiClient.test.js, navConfig.test.js, access.test.js, authFlow.test.js, workspaceSelection.test.js, format.test.js, stockEnquiryService.test.js
src/navigation/access.js
src/services/directoryService.js, workspaceSelection.js
```

Empty, not-yet-populated module folders exist at `src/modules/` for future
phases (per the spec's own proposed tree) — these are genuinely empty,
not fake placeholder screens; nothing in `navConfig.js` claims them as
`ready`.

## Sync / Device Control module — 2026-11-14

Request: "there is no device control and all sync related activities so
check this and wire all under sync menu." A new **Sync** nav group was
added (super-admin only, matching how `supplier-stock-client` gates its
own Sync Live / Schema Sync screens and how Device Controller is an
HO-admin surface) with four read-only screens, all reusing the existing
generic `WorkspaceModulePage` / `moduleRegistry.js` pattern — no new
bespoke UI component was written:

| Nav item | Route | Backend call |
|---|---|---|
| Sync Live | `/sync/live` | `GET /api/sync/control-center` |
| Sync History | `/sync/history` | `GET /api/sync/history?limit=50` + `GET /api/sync/history/statistics` |
| Store Health | `/sync/store-health` | `GET /api/sync/store-health` |
| Device Control | `/sync/device-control` | `GET /api/device-controller/devices` |

Source of truth for what exists: `backend/controllers/sync_admin_controller.py`
(prefix `/api/sync`, older MVC layout — NOT under `backend/modules/sync/`,
which only has the *agent-facing* runtime/catalog routers) and
`backend/modules/device_controller/router.py` (four routers: admin
`/api/device-controller`, agent `/api/agent/controller`, enrollment
`/api/auth/device-controller`, peer `/api/device-controller/peer` — only
the first is used, and only its GET `/devices` route, for now).

Deliberately NOT wired, because they are actions, not reads: `POST
/api/sync/tasks/create`, any `/api/sync/schedules*` or `/api/sync/tables*`
mutation, `/api/device-controller/devices/{id}/revoke`, `/commands`,
`/commands/bulk`, `/enroll-codes*`, `/terminals*` (remote-terminal session
start/input/close), and all of `schema_sync` (compare/apply push DDL
changes to a database — out of scope for a read-only app entirely, not
just this pass).

`presentTable.js`'s existing secret-key redaction (`token|password|secret|
pin|authorization|credential|api[_-]?key`, case-insensitive) covers device
rows without new code — a device's enrollment token or any credential-like
field is hidden by the same regex Administration's user list already
relies on.

Files touched: `src/navigation/navConfig.js` (new `sync` group, 4 items,
all `status: in_progress`), `src/navigation/access.js` (`SUPER_ONLY` set
extended with the 4 new ids — checked before the permissive module-filter
fallback, so a non-super-admin cannot see them regardless of module
grants), `src/modules/workspace/moduleRegistry.js` (4 new registry
entries), `src/app/App.jsx` (4 new routes, same `workspace(moduleId)`
helper already used for every other read-only screen). `tests/access.test.js`
gained a `sync screens are super-admin only` test plus an assertion that
the platform-user case still sees them; `tests/navConfig.test.js`'s exact
group-label list was updated to include `'Sync'`. `npm test`: **80/80
pass**. `npm run build`: exit 0, 85 modules.

Not yet live-UI-verified (no CDP pass done for this module, unlike Phase
5's Stock Enquiry) — only unit-tested and build-verified. The actual
`/api/sync/control-center`, `/api/sync/history`, `/api/sync/store-health`,
and `/api/device-controller/devices` response shapes have not been called
against a live backend from this app; `presentTable`'s generic column
inference means a wrong assumption fails open (an unexpected row shape
renders different columns, not a crash), but it has not been confirmed
against real data the way Phase 5's field names were.

## API contracts already in use (real, verified against backend source — do not re-invent)

| Endpoint | Verified against | Used by |
|---|---|---|
| `POST /api/auth/login` `{username, password}` → `{token, token_type, user}` | `backend/controllers/auth_controller.py:32-146` | `authService.js` |
| `POST /api/auth/logout` (Bearer auth) → `{ok: true}` | `backend/controllers/auth_controller.py:149-155` | `authService.js` |
| `GET /api/stock-availability/products/search?tenant_id=&q=&only_stock=` → `SearchResult` | `backend/modules/stock_availability/router.py:25-28`, `schemas.py` | `stockEnquiryService.js` — **live-verified 2026-11-14**, response shape matched exactly on the first real call |
| `GET /api/stock-availability/batches/search?tenant_id=&batch=&mrp=&product=` → `SearchResult` (same shape) | `backend/modules/stock_availability/router.py` | `stockEnquiryService.js` — wired as the "Batch / MRP" search mode, not independently live-tested this pass |
| `GET /api/stock-availability/products/core?tenant_id=&store_id=&product=&months=` → `{batches, purchases, sales, movement}` (raw SP rows, no Pydantic schema) | `backend/modules/stock_availability/service.py`/`repository.py` | `stockEnquiryService.js` → `ProductDetailPanel.jsx` — **live-verified 2026-11-14**; real field names are `snake_case` (`batch_no`, `date`, `pur`/`sal`/`tin`/`tout`/`adj`/`stk`, etc.), NOT the `PascalCase` originally guessed — see `05_STOCK_ENQUIRY_IMPLEMENTATION.md` §4/§6a for the full before/after |
| `GET /api/stock-availability/products/details?tenant_id=&store_id=&product=` | `backend/modules/stock_availability/router.py:68-70` | `stockEnquiryService.js` (defined, not yet called from any UI) |
| `GET /api/tenants` | `backend/controllers/tenant_controller.py` | `directoryService.js` — server already filters to the caller's tenant unless the caller has unrestricted scope |
| `GET /api/stores` | `backend/controllers/store_controller.py` | `directoryService.js` — inactive rows hidden in the client, same as supplier-stock-client |
| `GET /api/stores/tenant/{tenant_id}` | `backend/controllers/store_controller.py` | Used live to confirm a tenant switch. Not a new route. |
| `GET /api/sync/control-center` | `backend/controllers/sync_admin_controller.py` | `moduleRegistry.js` → Sync Live — not yet live-called from this app |
| `GET /api/sync/history`, `GET /api/sync/history/statistics` | `backend/controllers/sync_admin_controller.py` | `moduleRegistry.js` → Sync History — not yet live-called from this app |
| `GET /api/sync/store-health` | `backend/controllers/sync_admin_controller.py` | `moduleRegistry.js` → Store Health — not yet live-called from this app |
| `GET /api/device-controller/devices` | `backend/modules/device_controller/router.py` | `moduleRegistry.js` → Device Control — not yet live-called from this app |

The tenant sent by Stock Enquiry is the workspace selection: `user.tenant_id`
when the login has one, otherwise a tenant returned by `GET /api/tenants`.
The dev platform account has no `tenant_id`, which is why the switcher
exists. The renderer does not let the user type an id. The backend's
`assert_tenant_access` remains the authority. Nav hiding is not authorization.

## Web frontend (`frontend/`) rebrand — 2026-11-14

Separate from (not part of) the `desktop/nextech-mediq/` build phases, but
tracked here since it's the same brand identity: the owner was asked
whether the HO web frontend's login screen (still showing the old Axythic
mark) should also switch to NexTech MediQ. **Confirmed yes.** Changes
made, all in `frontend/`, none in either desktop client or
`desktop/nextech-mediq/` itself:

- Copied three SVG masters from `desktop/nextech-mediq/src/assets/branding/svg/`
  into `frontend/src/assets/` as `nextech-mediq-logo.svg` (light-bg
  lockup), `nextech-mediq-logo-dark.svg` (dark-bg lockup), and
  `nextech-mediq-mark.svg` (icon-only mark) — copies, not a shared/symlinked
  path, so `frontend/` has no runtime dependency on `desktop/`.
- `frontend/src/components/brand/Brand.tsx` — swapped `axythic-logo.svg`/
  `axythic-mark.svg` imports for the new assets; this is the shared
  component `Header.tsx` renders, so the main app shell's brand updated in
  one place.
- `frontend/src/pages/LoginPage.tsx` — swapped `axythic-logo-white.svg` →
  `nextech-mediq-logo-dark.svg` (dark showcase panel needs the
  light-colored lockup variant) and `axythic-mark.svg` →
  `nextech-mediq-mark.svg` (mobile brand row).
- `frontend/src/utils/appInfo.ts` — `APP_NAME` changed from `'Axythic Pharma'`
  to `'NexTech MediQ'` (only consumer was `LoginPage.tsx`, verified by grep
  before changing).
- `frontend/index.html` — `<title>` changed from `Axythic Pharma` to
  `NexTech MediQ`.
- `frontend/public/favicon.png` — replaced with a 128×128 resize of
  `nextech-mediq-app-icon.png` from the same brand pack (original was
  84×102, presumably an old Axythic export). `favicon.svg` in the same
  folder was found to be an orphaned old Axythic asset (not referenced by
  `index.html` or anywhere else via grep) — left in place, not deleted.
- Three Excel-export files set `wb.creator = 'Axythic'` as file metadata:
  `frontend/src/pages/nmw-sales/exportNmwBill.ts`,
  `frontend/src/pages/expiry-stock/exportExpiryStockExcel.ts`,
  `frontend/src/pages/expiry-report/exportExpiryExcel.ts` — all three
  changed to `'NexTech MediQ'`.
- `frontend/src/assets/axythic-logo.svg` and `axythic-logo-white.svg` are
  now orphaned (no remaining importers, verified by grep) — left in place,
  not deleted.
- `npm run build` in `frontend/` verified successful after all changes
  (exit 0, full chunk list produced, no errors).
- **Not yet verified live in a browser** — only build-verified, same
  caveat as the desktop app's own unverified-live state.

## Known open items / owner decisions still outstanding

Carried over from Phase 1 discovery (`01_PHASE1_ARCHITECTURE_DISCOVERY.md`
§7), still unresolved:

1. Whether the Quick Stock kiosk workflow and the new Stock Enquiry module
   are genuinely two different use cases (kiosk vs. logged-in operator) or
   should converge — not resolved, both are being built as currently
   distinct (Stock Enquiry is now built; Quick Stock integration has not
   started).
2. Tenant/store sourcing — **resolved 2026-11-14**. `user.tenant_id` is
   not enough: the dev platform login has none. The top bar selects a
   tenant and store from `GET /api/tenants` and `GET /api/stores`. A saved
   id the directory does not return is dropped. Server-side tenant checks
   are unchanged.
3. Procurement integration (Phase 8) remains blocked on the Phase 7C
   consolidation investigation's unresolved owner decisions (see
   `docs/NEXORA_LEGACY_CONSOLIDATION/13_UNKNOWNS_AND_OWNER_DECISIONS.md`) —
   do not start Phase 8 business-logic work until those are resolved.

## Non-negotiable constraints for whoever continues this work

- Never edit, delete, or import-at-runtime anything under
  `desktop/supplier-stock-client/` or `desktop/quick-stock-client/`.
- Never add direct database/SQL access to the Electron renderer.
- Never invent a new backend endpoint — if a needed capability has no
  existing API, document it as a missing dependency and stop, don't guess.
- Never submit a real supplier order or touch a production database.
- Keep `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`
  on every BrowserWindow — do not loosen this without a documented reason
  (e.g. a future webview requirement, mirroring why
  supplier-stock-client sets `sandbox: false`).
- Update this file at the end of every phase — status table, "what
  actually works," and "what has NOT been verified" sections especially.
