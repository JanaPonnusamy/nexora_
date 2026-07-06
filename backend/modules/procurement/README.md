# Procurement Module

End-to-end procurement for the UniNex platform: Business Cycle → Refresh →
Decision Engine (VPL) → Purchase Manager review → Supplier Assignment → Export →
GRN reconciliation → Pending → Next Refresh → Cycle close.

## Architecture

Layered, all business rules in Python; SQL only for data access and bulk ops.
No stored procedures for business logic. Raw `pyodbc` repositories (platform
convention — no ORM).

```
router / *_router  →  *_service (orchestration + validation + logging)
                      → *_rules   (pure business rules, unit-tested)
                      → *_repository (pyodbc; parameterized SQL; bulk writes)
                      → _dbutil    (shared rows_to_dicts / stringify)
```

Pure rule modules (no I/O, fully unit-tested): `decision_rules`,
`reconciliation_rules`, `refresh_comparison`.

## Data model (schema `procurement`, migrations `sql/0001`–`0008`)

| Table | Purpose |
|-------|---------|
| `procurement_cycles` | Business Cycle header + GRN/Sale-Bill boundaries, `active_refresh_id`, status |
| `procurement_refreshes` | Immutable Refresh (snapshot params, GRN completion markers) |
| `procurement_virtual_products` | Immutable VPL — decision snapshot + explainability |
| `procurement_order_items` | Working Order Items (review, pending = `remaining_qty`) |
| `procurement_order_item_assignments` | Supplier assignment + export metadata + GRN receipts |

No Pending table (pending = `remaining_qty > 0`). No Export Header (export
metadata on the assignment). Conventions: `<entity>_id` PKs, `VARCHAR`/`DATETIME`,
audit `created_at/created_by/updated_at/updated_by` (GUID users), soft delete
`is_deleted/deleted_at/deleted_by`, unnamed inline constraints — matching
`installer/sql/001_platform_foundation.sql`.

Indexes: every table is indexed on `(tenant_id, is_deleted)` and by owning key
(`refresh_id` / `order_item_id`); assignments add `export_batch_number` and
`supplier_code` indexes; VPL/order-item joins ride the unique
`(refresh_id, product_id)` index. No N+1 — reads are single queries and writes
are bulk (`INSERT…SELECT`, `fast_executemany`).

## API (prefix `/api/procurement`)

Lifecycle: `POST /cycles/open`, `POST /cycles/{id}/refreshes`,
`POST /cycles/{id}/close`.
Workspace: `GET /refreshes/{id}/workspace`, `GET /order-items/{id}`,
`PUT /order-items/{id}/final-qty`, `POST …/restore-suggested`, `…/skip`,
`…/restore`, `GET /order-items/{id}/decision`.
Suppliers: `GET /order-items/{id}/supplier-queue`, `GET /suppliers/search`,
`GET /suppliers/{code}/stats`.
Assignment: `GET/POST /order-items/{id}/assignments`, `POST /assignments/bulk`,
`PUT /assignments/{id}/supplier`, `DELETE /assignments/{id}`.
Export: `POST /refreshes/{id}/export`, `GET /refreshes/{id}/export-history`,
`GET /exports/{batch}`.
GRN/Pending: `POST /refreshes/{id}/grn`, `GET /refreshes/{id}/pending`,
`PUT /order-items/{id}/pending`, `POST …/pending/skip`, `…/pending/carry-forward`,
`POST /refreshes/{id}/pending/finalize`, `POST /refreshes/{id}/manual-items`.

Conventions: `tenant_id` is a required query param; bodies are Pydantic
(`schemas.py`, `vpl_schemas.py`, `pm_schemas.py`); errors are `HTTPException`
(400 validation, 404 not-found, 409 conflict, 403 missing acting user).

## Security / RBAC

All SQL is parameterized (`?`); the only interpolated fragments are an
integer-cast `TOP (n)`, a whitelisted `ORDER BY`, and `?`-placeholder `IN (…)`.
Every query is tenant-scoped. Procurement defines no roles; `created_by` /
`reviewed_by` / `exported_by` / `closed_by` are the RBAC seam — services require
the acting user and the platform permission check plugs in there
(`procurement.cycle.*`, `procurement.refresh.*`, workspace permissions).

## Logging

`logging.getLogger("procurement.<area>")` per service; every business action
logs at INFO (cycle, refresh, review, assignment, export, GRN, pending, close),
failures via `logger.exception`. Services roll back and re-raise — no swallowed
exceptions.

## Operational integration points (platform-owned, isolated behind repos)

Product Master, Sales, Stock, PurchaseTrans, Store Sync, Supplier Purchase
History. Each is a single marked seam that returns an empty/neutral result until
wired (`decision_repository.load_source`, `reconciliation_repository`
`read_purchase_receipts`, `reconciliation_service._trigger_store_sync`,
`supplier_repository`). Wiring them changes no rules, services or APIs.

## Tests

`tests/test_procurement_*.py` — 67 DB-free tests: schema/convention, decision
engine, orchestration, PM workflow, and Sprint-3 (GRN, pending, comparison,
close, decision explorer, stubbed end-to-end). Pure-rule modules are exhaustively
tested against the frozen worked examples.
