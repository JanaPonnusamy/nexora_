# NexTech MediQ Workspace — complete workspace integration

Date: 2026-11-14. App: `desktop/nextech-mediq` only. Electron stayed at 22.3.27. `contextIsolation` remains true and `nodeIntegration` remains false. No renderer SQL. No new backend route. No production host, production database, purchase-order submit, sales-order submit, fleet action, update feed, or production certificate was used. Existing desktop clients were not edited.

## 1. Purpose

This pass turns the shell into one operational workspace for the read workflows that already have a working API. Write workflows that submit orders, change stock, send WhatsApp, repair data, or import files were left unwired on purpose.

## 2. Identity and boundaries

Product name: NexTech MediQ Workspace. App id: `com.nextech.mediq.workspace`. The app is a third desktop client. `desktop/supplier-stock-client`, `desktop/quick-stock-client`, and `desktop/order-management-client` were not modified. Git still shows earlier dirty files under supplier-stock-client and an untracked quick-stock-client tree; those were already present and were not written in this pass.

The API base URL comes from `VITE_API_BASE_URL` (`.env.development` and `.env.production` are `http://127.0.0.1:8000`). A host saved in settings is ignored. `192.168.10.32` is refused if it appears in that env value.

## 3. Module inventory

| Module | Source | Frontend that already had it | API this workspace calls | Permission | What it does | Workspace status | Remaining | Evidence |
|---|---|---|---|---|---|---|---|---|
| Dashboard | New shell | This app | None of its own. Directory comes from login. | Any signed-in user except stock-only and label-review | Landing map of visible modules | COMPLETE as a landing page | No operational widgets beyond the map | Electron heading Dashboard after login |
| Stock Enquiry | Stock availability | This app, web stock availability | `GET /api/stock-availability/products/search`, batches search, product core | Stock module grant, unless the role is unrestricted | Product and batch search, branch grid, detail | COMPLETE. Not rebuilt | None in this pass | HTTP 200, 6 store cards for q=para. Electron grid rendered 126 rows after typing para |
| Network stock | Non-moving analysis | Web / stock client analysis | `GET /api/non-moving-analysis/stores` | Purchase or admin on the server; the client shows it with stock navigation | Branch list for the analysis | COMPLETE for the store list | The per-store dashboard did not return during a long wait, so the screen does not call it | HTTP 200, 6 stores |
| Non-moving stock | Non-moving report | Web non-moving report | `GET /api/non-moving-report/data` | Tenant access | Dwell report | COMPLETE | Zero rows for the first store at 90 days. That is an empty result, not sample data | HTTP 200, rows 0 |
| Stock check | Stock check report | Web stock check | `GET /api/stock-check-report/sublocations` and `/rows` when a code is typed | Tenant access | Sublocation sheet | COMPLETE for the lookup | The count sheet itself was not opened with a chosen range in Electron | HTTP 200, 20 sublocations |
| Stock integrity | Stock integrity | Web | `GET /api/stock-integrity/report` | Tenant access | Compare batch stock with product totals | COMPLETE | Repair is not called. The live report had 0 mismatch rows | HTTP 200, rows 0 |
| Product mapping | Product mapping | Web | `GET /api/product-mapping/products/search` | Tenant access | Store product search | COMPLETE for search | Approve / remap are not sent | HTTP 200, 5 products for q=para |
| NMW sales | NMW sales report | Web | `GET /api/nmw-sales-report/bills` | Server scopes the caller | Dispatch bills | PARTIAL | The call did not return within 40 seconds | AbortError |
| Supplier stock | Supplier stock analysis | supplier-stock-client | `GET /suppliers` and `GET /search` | Admin-tier on the server | Supplier list and product search | COMPLETE for those reads | Import, mapping write, assignment save | HTTP 200, 12 suppliers and 5 search items. Electron table rendered |
| Quick stock | Quick stock kiosk | Web /quick-stock, quick-stock-client | `POST /api/quick-stock/verify`, `GET /products/search` with x-quick-stock-pin | Passcode, not the JWT | Counter search | PARTIAL | Electron page was not driven. A wrong passcode returned 401 and did not clear the workspace session | HTTP 401 wrong pin, HTTP 200 verify, HTTP 200 search, 6 stores |
| Rate analysis | Rate analysis | Stock client | `GET /api/rate-analysis/suppliers?days=30` | Purchase or admin | Supplier purchase value | COMPLETE for 30 days | 90-day request did not return within 20 seconds. Quote compare is not sent | HTTP 200, 160 suppliers, 5 store codes |
| Procurement workspace | Procurement cycles | Web purchase workspace | `GET /api/procurement/cycles` | Tenant access | Cycle list | COMPLETE | No cycle create, refresh, or PO | HTTP 200, total 28. Electron table rendered |
| Procurement rules | Rules registry | Web rules page | `GET /api/procurement/rules/catalog` | Procurement admin | Catalog | COMPLETE | Overrides are not saved | HTTP 200, 24 rules |
| Order workspace | Legacy order | Web order workspace | `GET /api/legacy-order/orders/{store}` | Order console | Current order grid | COMPLETE as a read | Finalize, assign, export are not called | HTTP 200, 846 rows for the first returned branch |
| Order entry | Legacy order | Web order entry | `GET /api/legacy-order/orders/{store}/order-entry` | Order console | Readiness only | COMPLETE as a read | POST start-order is not called | HTTP 200, object body |
| Legacy order | Legacy order | Web legacy console | `GET /db/health`, `GET /stores` | Super / platform in the client nav; server still checks | Health and branches | COMPLETE for those reads | Recovery, repair, and sync are not called | HTTP 200 health, 6 stores |
| Sales reports | Reports module | Web reports | `GET /api/reports` catalog only | Not salesman | Catalog | PARTIAL | Running a report is withheld. The server replaces an empty result with unlabeled sample rows | HTTP 200, 10 catalog entries |
| Expiry report | Expiry report | Web | `GET /api/expiry-report/store-summary` | Tenant access | Store summary | COMPLETE | Line-level expiry-stock (2812 rows on GET /api/expiry-stock/report) was checked over HTTP and is not a separate screen | HTTP 200, 5 summary rows |
| Sale analysis | Sale analysis | Web | `GET /api/sale-analysis/products` | Store access | Product lookup | COMPLETE for lookup | Group save is not sent | HTTP 200, 5 products |
| Time report | Time report | Web | `GET /api/time-report/meta` | Not salesman in the client | Attendance source metadata | COMPLETE for metadata | Daily and monthly sheets were not opened | HTTP 200, 5 reports, 6 departments, 140 users |
| AI intelligence | Shelf-sort classify | Web training page, this app | `GET /api/procurement/shelf-sort/categories` this pass. Classify remains the only model call in the client | Procurement workspace on classify | Vocabulary list. Classify still requires an explicit acknowledgement and does not change stock | PARTIAL | Classify was not posted this pass because it stores unconfirmed suggestions | HTTP 200, 23 categories. Unit tests still cover the classify contract |
| Administration | Users | Web platform users | `GET /api/users` | Server filters by tenant unless the caller is unrestricted. The client shows the item to platform users | User directory | COMPLETE for the list | Create, edit, and role assignment are not sent | HTTP 200, 23 users |
| Settings | This app | This app | None | Signed-in users who can see settings | Version and session note | PARTIAL | The screen was not opened in Electron this pass. The API host field is gone | Code review |

## 4. Shared shell

One shell remains: AppShell, grouped sidebar from navConfig plus visibleNavGroups, header, breadcrumbs, tenant and store selectors, user menu, and the existing light/dark control. New screens use PageLayout and WorkspaceModulePage. They do not bring their own chrome. Tokens stay the `--ntm-*` set. A direct hash to a route the role cannot see still redirects through resolvePathForUser. Hiding a menu item is not the authorization check; the API remains the authority.

## 5. Authentication and session

Login, logout, restore, expiry, tenant, store, and bearer headers are the Phase 4 behavior with two changes.

The token is not written to localStorage. setSession keeps it in renderer memory and, when "Remember this session on this device" is checked, asks the main process to encrypt it with safeStorage into session.vault under the Electron user-data directory. If encryption is unavailable, the file is not written in plaintext. An old nextechMediq.session value is read once and deleted.

This is not server revocation. POST /api/auth/logout returned 200 for the platform user, and the same bearer then received GET /api/tenants 200. Full-access tokens have no session id.

A 401 from the quick-stock passcode check uses skipAuth, so it does not clear the workspace session. A 401 on a normal bearer request still clears it. 403, 404, 422, 500, and network failures surface as the existing ApiError text on the workbench.

## 6. Login screen

The normal login form shows branding, the tagline, username, password, show/hide, remember-session, sign-in, loading, and auth errors, plus a version footer. There is no API URL, host, or developer connection field. Electron confirmed input name apiBaseUrl and input type url were absent, and sign-in reached the dashboard.

## 7. Stock Enquiry

The Phase 5 page, service, grid, keyboard path, and product-core panel were not rewritten. Live search still returns the branch payload the grid already understands.

## 8. How rows are shown

presentTable uses an array the API actually returned (rows, items, suppliers, products, and the same kind of key). When the payload includes columns, those keys are the headers. Nested branch/product cards are flattened with the store name. Keys whose names look like a token, password, or passcode are not rendered. The screen does not invent a column the payload did not have.

## 9. What was deliberately not integrated

| Area | Why |
|---|---|
| Report run (`GET /api/reports/{key}` and the non-moving highlight route) | The service substitutes unlabeled sample rows when the query is empty or throws. Showing that as live data is not allowed. |
| Purchase-order submit, cycle create, refresh build, assignment, export, legacy POST order-entry, order process, sync, stock update | These submit or mutate operational data. |
| Stock integrity repair, emergency DB repair, distribution send, WhatsApp send, excel import | Writes, and in one case a data-loss repair. |
| Sync admin, device control, remote terminal, licensing, update feeds | Out of the workspace scope and unsafe to drive from this client. |
| Document extraction, label exporter, pass generation | Not required to make a read workflow true, and pass generation is credential-adjacent. |
| Non-moving analysis dashboard | The request did not return during a wait of more than two minutes. The store list is shown instead. |
| Shelf-sort classify this session | It persists unconfirmed suggestions. The client still has the button and the unit tests. It was not posted again. |

## 10. Design

Login, settings, and the new workbench use the existing navy/slate panels and teal actions. Settings no longer offers an API host. The workbench is a dense filter row, sticky header table, and pager. Empty, loading, and error states are the shared components.

## 11. Tests

`npm test` from `desktop/nextech-mediq`: exit code **0**. **79 passed, 0 failed.** New coverage: the session is not written to localStorage, a saved API host is ignored, a skipAuth 401 does not drop the workspace session, and table shaping drops secret-looking keys.

Mocked: auth, session, API client errors, permissions, stock enquiry service, AI classify contract, table shaping.

Live: the HTTP list in section 13 and the Electron path in section 14.

Not tested live: non-platform roles, manual hash bypass in the window, batch/MRP mode this pass, product detail this pass, settings page click, quick-stock page click, NMW bills.

Backend pytest was not run. No backend file was changed.

## 12. Production build

`npm run build` exit code **0**. 85 modules. `dist/assets/index-Cz2fS8fj.js` 246.37 kB (gzip 78.25 kB). `dist/assets/index-xGM5fnha.css` 22.82 kB (gzip 4.48 kB). The same Vite step ran again inside the successful `npm run dist`.

## 13. Live HTTP

Against `http://127.0.0.1:8000` with the existing dev login. The password and token are not recorded. Invalid password: **401**. Valid login: **200**, platform user, no tenant id, 1 role, 26 modules. Tenants **200** (3). Stores **200** (10). Logout **200**, then tenants again **200** with the same bearer.

Other live results are in the inventory table. Nothing was posted except login, logout, and quick-stock verify.

## 14. Electron launch

`ELECTRON_RUN_AS_NODE` was removed from the child environment. Electron 22.3.27 was started on the Vite dev server with a fresh user-data directory and `--remote-debugging-port=9334`. CDP drove the real inputs.

| Check | Result |
|---|---|
| Window title | NexTech MediQ Workspace |
| API field | Absent |
| Username, password, show, remember, sign-in | Present |
| After sign-in | Heading Dashboard, hash `#/dashboard` |
| Stock Enquiry | Heading Stock Enquiry, 126 grid rows after para |
| Supplier Stock | Heading Supplier Stock, table rows, no alert |
| Procurement | Heading Procurement Workspace, table rows, no alert |

The process was then stopped with taskkill so packaging could copy Electron. That stop was not a crash during the script. The CDP script exited 0.

## 15. Packaging

First `npm run dist`: Vite succeeded, electron-builder 24.13.3 started `release\win-unpacked` for Electron 22.3.27, then exited **1**. 7-Zip could not create the macOS symlinks inside the winCodeSign cache (`Cannot create symbolic link : A required privilege is not held by the client`). No production certificate was used.

`package.json` `dist` now passes `--config.win.signAndEditExecutable=false`. Second `npm run dist`: exit code **0**. Artifact: `desktop/nextech-mediq/release/NexTechMediQWorkspace-Setup-0.1.0.exe` plus its blockmap. Unsigned. Not published. The executable icon is not rewritten by the code-sign tool because that step is what required the symlink.

## 16. Completion matrix

COMPLETE means the workflow's read call returned and the screen is wired. It does not mean every button in the legacy app was copied. PARTIAL means the screen exists but the live call failed, was withheld, or was not driven in Electron when that was the only proof.

| Module | Status |
|---|---|
| Dashboard | COMPLETE |
| Login, logout, session restore | COMPLETE |
| Tenant and store directory | COMPLETE |
| Stock Enquiry | COMPLETE |
| Network stock store list | COMPLETE |
| Non-moving report | COMPLETE |
| Stock check sublocations | COMPLETE |
| Stock integrity | COMPLETE |
| Product mapping search | COMPLETE |
| NMW sales bills | PARTIAL |
| Supplier stock reads | COMPLETE |
| Quick stock | PARTIAL |
| Rate analysis, 30 days | COMPLETE |
| Procurement cycle list | COMPLETE |
| Procurement rules catalog | COMPLETE |
| Order workspace read | COMPLETE |
| Order entry readiness | COMPLETE |
| Legacy health and stores | COMPLETE |
| Sales report catalog | PARTIAL |
| Expiry store summary | COMPLETE |
| Sale analysis lookup | COMPLETE |
| Time report metadata | COMPLETE |
| AI vocabulary | PARTIAL |
| Administration user list | COMPLETE |
| Settings | PARTIAL |
| Order submit, PO submit, sync, device control, report execution | BLOCKED |
