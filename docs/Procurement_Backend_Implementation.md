# Procurement Backend — Implementation Reference

Living technical reference for the `backend/modules/procurement/` module.
Covers the foundation backend only — no business intelligence (calculation,
supplier, pending, shortage, expiry, purchase-order, export) is implemented
yet. Those arrive in later sprints.

| Sprint | Scope | Status |
|--------|-------|--------|
| 1 | Procurement Workspace + Procurement Cycle CRUD | Done |
| 2 | Virtual Product List (VPL) + VPL Products | Done |

All tables live in the `procurement` schema of **NEXORA_PLATFORM** (SQL Server).
Every row is multi-tenant aware (`tenant_id`), audited, and (headers) soft
-deletable. Every query is tenant-scoped.

---

## Sprint 2 — Virtual Product List (VPL)

### Architecture

The VPL is a **snapshot workspace**: the set of products selected for a given
procurement cycle, frozen as identity + metadata. It is the foundation every
later procurement stage reads from (product selection, supplier assignment,
calculation, etc.).

The VPL deliberately stores **only product identity and snapshot metadata** —
no order quantities, stock figures, supplier links, or computed values. This
keeps the snapshot stable and lets later engines layer their own derived data
without mutating the source-of-truth list.

A VPL header moves through a status lifecycle:

```
Draft ──refresh──► Refreshing ──► Ready ──archive──► Archived
  ▲                                  │
  └──────────── refresh ◄────────────┘
```

- **Draft** — newly created, products being added/removed.
- **Refreshing** — transient state while metadata is re-stamped.
- **Ready** — snapshot consistent and usable by downstream stages.
- **Archived** — immutable; no product changes, no further refresh.

`refresh` re-stamps products (bumps `snapshot_version`, updates `modified_on`)
and returns the VPL to **Ready**. It does **not** compute or fetch business
data — that is intentionally deferred.

### Entity Relationships

```
procurement_workspace (1) ──< procurement_cycle (1) ──< procurement_virtual_product_lists (1) ──< procurement_virtual_products
        workspace_id              cycle_id                       vpl_id (id)                              product rows
```

- A **cycle** belongs to a **workspace** (validated on VPL create).
- A **VPL** belongs to one workspace + one cycle (FKs enforce existence).
- **VPL products** belong to one VPL; a product appears at most once per VPL
  (`UQ_proc_vp_vpl_product` on `(vpl_id, product_id)`).

### Database Schema

Migration: `backend/modules/procurement/sql/0002_virtual_product_list.sql`
(idempotent).

#### procurement.procurement_virtual_product_lists

| Column | Type | Notes |
|--------|------|-------|
| id | uniqueidentifier | PK, default NEWID() |
| tenant_id | uniqueidentifier | NOT NULL, tenant scope |
| workspace_id | uniqueidentifier | NOT NULL, FK → procurement_workspace |
| cycle_id | uniqueidentifier | NOT NULL, FK → procurement_cycle |
| store_id | uniqueidentifier | NULL (tenant-wide when null) |
| snapshot_name | nvarchar(200) | NOT NULL |
| snapshot_status | varchar(20) | Draft \| Refreshing \| Ready \| Archived (CHECK) |
| created_by | nvarchar(100) | audit |
| created_on | datetime2(3) | audit, default SYSUTCDATETIME() |
| modified_by | nvarchar(100) | audit |
| modified_on | datetime2(3) | audit |
| deleted_on | datetime2(3) | soft delete (NULL = live) |

#### procurement.procurement_virtual_products

| Column | Type | Notes |
|--------|------|-------|
| id | uniqueidentifier | PK, default NEWID() |
| tenant_id | uniqueidentifier | NOT NULL |
| workspace_id | uniqueidentifier | NOT NULL (denormalised from VPL) |
| cycle_id | uniqueidentifier | NOT NULL (denormalised from VPL) |
| vpl_id | uniqueidentifier | NOT NULL, FK → procurement_virtual_product_lists |
| product_id | uniqueidentifier | NOT NULL |
| product_code | nvarchar(100) | identity |
| product_name | nvarchar(300) | identity |
| manufacturer_id | uniqueidentifier | identity |
| category_id | uniqueidentifier | identity |
| schedule_type | nvarchar(50) | identity |
| unit | nvarchar(50) | identity |
| is_active | bit | default 1 |
| snapshot_version | int | default 1, bumped on refresh |
| created_on | datetime2(3) | audit |
| modified_on | datetime2(3) | audit |

> Unique constraint `(vpl_id, product_id)` prevents duplicate products.
> Product removal is a hard delete (the products table has no soft-delete
> column); the VPL header carries the soft delete.

### API Endpoints

All under `/api/procurement/vpl`. `tenant_id` is required on every call
(tenant isolation). List endpoints support pagination (`page`, `page_size`),
`search`, and filters.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/procurement/vpl` | Create VPL (validates workspace + cycle) |
| GET | `/api/procurement/vpl` | List VPLs — filters: `workspace_id`, `cycle_id`, `store_id`, `status`, `search` |
| GET | `/api/procurement/vpl/{vpl_id}` | Get VPL |
| POST | `/api/procurement/vpl/{vpl_id}/refresh` | Refresh metadata → Ready |
| POST | `/api/procurement/vpl/{vpl_id}/archive` | Archive VPL |
| DELETE | `/api/procurement/vpl/{vpl_id}` | Soft delete VPL |
| POST | `/api/procurement/vpl/{vpl_id}/products` | Add product (duplicate-checked) |
| GET | `/api/procurement/vpl/{vpl_id}/products` | List products — `search`, pagination |
| DELETE | `/api/procurement/vpl/{vpl_id}/products/{product_row_id}` | Remove product |

### Validation Rules

- **Tenant isolation** — every read/write filters by `tenant_id`.
- **Workspace exists** — VPL create rejects unknown/deleted workspace (400).
- **Cycle belongs to workspace** — VPL create verifies the cycle's
  `workspace_id` + tenant (400).
- **VPL status** — archived VPLs reject refresh / archive / product add /
  product remove (409).
- **Duplicate product prevention** — adding an existing `product_id` to a VPL
  returns 409 (also enforced by the unique index).

### Source Files

| File | Role |
|------|------|
| `sql/0002_virtual_product_list.sql` | Migration |
| `vpl_schemas.py` | Request/response models |
| `vpl_repository.py` | Tenant-scoped data access |
| `vpl_service.py` | Orchestration + validation |
| `vpl_router.py` | REST endpoints (mounted on main `router`) |

The VPL sub-router is mounted onto the module's main `router`
(`router.include_router(vpl_router)`), which is already registered with the
FastAPI app, so the endpoints are live without further app wiring.

---

## VPL Comparison (runtime operation — NOT an entity)

Comparison is **not** a business entity. There is **no** `compare_session`,
`compare_session_items`, `procurement_compare`, comparison or comparison-history
table, and comparison results are **never persisted**. (The legacy
`compare_session_items` concept is explicitly **not** adopted.)

Each Procurement Refresh already produces an immutable VPL snapshot. A
comparison is a read-only, on-the-fly diff between two snapshots:

```
Source Refresh (VPL A)  VS  Target Refresh (VPL B)
```

- Both VPLs must belong to the same `tenant_id`, `workspace_id` and `cycle_id`.
- Products are matched by `product_id` via a single optimised SQL
  `FULL OUTER JOIN` over `procurement_virtual_products` (filtered by
  `source_vpl_id` / `target_vpl_id`). The diff, difference and change type are
  computed in SQL; the dataset is never materialised in Python.
- The compared quantity is `final_required_qty` (NULL treated as 0).

**Change types:** `Added`, `Removed`, `Increased`, `Decreased`, `NoChange`.

### Endpoint

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/procurement/vpl/compare` | Compare two VPL snapshots |

Params: `source_vpl_id`, `target_vpl_id`, `tenant_id` (required); optional
`changed_only`, `action_filter`, `search`, `page`, `page_size`. Each row returns
previous (`source_qty`) / current (`target_qty`) values, `qty_difference`, and
`change_type`. The compare route is mounted before the VPL router so
`/vpl/compare` is not captured by `/vpl/{vpl_id}`.

### Source files

`compare_repository.py` (read-only query), `compare_service.py` (validation +
orchestration), `compare_router.py` (endpoint). No migration — no tables.
