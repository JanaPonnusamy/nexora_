# 05 — API and Database Dependencies
**NEXORA MEDIQ Unification — Phase 0 Audit**

## Renderer → Backend coupling

All backend calls from the desktop app go through one file: `desktop/supplier-stock-client/src/api/client.js` (1743 lines, one `api` object, ~80+ methods, one `request()` wrapper). This is the single integration seam for any future work — a future rewrite of the frontend can keep this file largely as-is and swap only the UI layer above it.

Endpoint groups identified (VERIFIED against matching backend modules unless noted):

| Prefix | Backend location | Verification |
|---|---|---|
| `/api/auth/*` | `backend/controllers/auth_controller.py` (254 lines) | VERIFIED, read in full |
| `/api/stock-availability/*` | `backend/modules/stock_availability/` | Present per prior project memory, not re-read this pass |
| `/api/supplier-stock-analysis/*` | `backend/modules/supplier_stock_analysis/repository.py` | VERIFIED present |
| `/api/legacy-order/*` | `backend/modules/legacy_order/` | VERIFIED present; actively developed (most recent commit) |
| `/api/sync/*`, `/api/schema-sync/*` | sync/schema-sync backend | Present, matches `SyncLive.jsx`/`SchemaSyncPage.jsx` |
| `/api/whatsapp/*` | `backend/modules/whatsapp/service.py` | VERIFIED present |
| `/api/time-report/*`, `/api/rate-analysis/*`, `/api/nmw-sales-report/*` | matching backend routers | **INFERRED** present (consistent naming, no broken-call symptoms observed) — not individually re-read |
| `/api/desktop-client/activate/*`, `/api/ho-routes`, `/api/tenants`, `/api/stores`, `/api/bootstrap/routes` | device/tenant bootstrap | VERIFIED present |
| `/api/procurement/*` | `backend/modules/procurement/pm_router.py` (1193 lines) | VERIFIED, read in detail — largest and most actively developed surface |

## Procurement backend detail

`pm_router.py` backs: supplier queue/assignment, GRN submission, pending-order adjustment, abnormal-sales review, the shelf-sort AI classifier (`shelf_sort_service.py`), and — as of this audit, **uncommitted** — new tenant export-defaults endpoints (`GET/PUT /api/procurement/export-defaults`), backed by a new table `procurement.tenant_export_defaults` (migration `sql/0032_tenant_export_defaults.sql`) and `tenant_export_defaults_repository.py`.

## Database access pattern

- SQL Server access happens **only from the FastAPI backend.** No ODBC/mssql client library exists anywhere in the Electron app (main process, preload, or renderer).
- The Electron main process (`main.cjs`, `preload.cjs`) exposes no SQL or arbitrary filesystem access to the renderer — confirmed by absence of any DB client `require()` in those files. Export file writes are restricted to `.xls/.xlsx/.csv` plus explicit open/choose-folder dialogs (main.cjs:184-203), not general file I/O.
- This means any unified NEXORA MEDIQ frontend can be built entirely against the existing backend API surface — **no new direct database contracts need to be designed** for the UI unification itself. New capability (e.g., AI Intelligence Centre features) would need new backend endpoints, but not a new database access pattern.

## What could not be verified

- Full completeness of `/api/time-report`, `/api/rate-analysis`, `/api/nmw-sales-report` router implementations — not read line-by-line.
- Whether `tenant_export_defaults_repository.py`'s new migration has been tested against a live database (it is uncommitted work-in-progress, not yet merged).
- `order-management-client`'s `HoApiClient.cs` was not independently re-verified to confirm it never opens a direct DB connection — this is taken from its own README.
