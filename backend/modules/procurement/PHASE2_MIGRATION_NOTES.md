# Procurement Phase 2 — Migration & Backward-Compatibility Notes

Schema-refactoring sprint aligning `procurement.*` to NEXORA_PLATFORM
conventions. See the approved rulings in the Phase 1 review.

## What changed (DDL)

| Table | Change |
|-------|--------|
| `procurement_cycles` | −`rolling_days`, −`generated_product_count`, −`live_refresh_count`, −`last_refresh_id`; +`start/end_grn_number`, +`start/end_sale_bill_number`; kept `active_refresh_id` |
| `procurement_refreshes` | PK `id`→`refresh_id`; +`rolling_days`, +`previous_refresh_id`, +`snapshot_grn_number`, +`snapshot_sale_bill_number`, +`sync_execution_id`; **no** `previous_pending_ref`, **no** `generation_duration` |
| `procurement_virtual_products` | PK `id`→`virtual_product_id`; FK `vpl_id`→`refresh_id`; +`effective_available_qty`, +`pending_used_qty` |
| `procurement_order_items` | PK `id`→`order_item_id`; FK `vpl_id`→`refresh_id`; `item_status` set = draft \| review \| assigned \| partial \| skipped |
| `procurement_order_item_assignments` | PK `id`→`assignment_id`; +`export_batch_number`, +`export_split_number`, +`export_uid`, +`exported_at`, +`exported_by` |

Conventions applied to every table: `VARCHAR` (not `NVARCHAR`), `DATETIME`
(not `DATETIME2`), unnamed inline constraints, audit
`created_at`/`created_by`/`updated_at`/`updated_by` with user refs as
`UNIQUEIDENTIFIER`, soft delete `is_deleted`/`deleted_at`/`deleted_by`.

## How to apply

- **Fresh install:** run `sql/0001`→`0005` (and `0003`) in order — they emit the
  final schema. Then run `sql/verify_phase2_alignment.sql` (prints `PHASE 2 OK`).
- **Existing dev DB on the pre-refactor scaffolding:** these tables were created
  in release 0.3.0 as a schema freeze and hold **no business data**, and the
  `IF OBJECT_ID ... IS NULL` guards make the base scripts skip already-created
  tables. Drop the five `procurement.*` tables (and re-create the schema) then
  re-run the migrations. No data migration is required because no procurement
  business rows exist yet.

## Backward-compatibility review

- **No business data at risk.** Procurement is pre-release scaffolding; there are
  no rows to migrate and no external consumers in production.
- **API response contract changed** (intentional convention fix): Refresh/VPL
  responses now return `refresh_id` (was `id`) and product rows return
  `virtual_product_id`/`refresh_id` (was `id`/`vpl_id`); Cycle audit user fields
  are GUIDs. The path parameter stays `/vpl/{vpl_id}` (its value is the
  `refresh_id`). No frontend consumes the Procurement API yet, so no UI break.
- **`created_by`/`updated_by`/`deleted_by` are now `UNIQUEIDENTIFIER`.** Callers
  must pass a user GUID string (pyodbc binds it to `UNIQUEIDENTIFIER`). The
  `?by`/`?deleted_by` query params are optional and default to NULL, so existing
  calls that omit them keep working.
- **Timestamps** now use `GETDATE()` (local, platform standard) instead of
  `SYSUTCDATETIME()`.

## Deliverable note — SQLAlchemy models

The requested "SQLAlchemy models" deliverable was intentionally **not**
produced: the backend uses raw pyodbc repositories (the only ORM model,
`backend/models/user_model.py`, is unused by any module). Adding SQLAlchemy to
Procurement would introduce a convention the platform does not use. The existing
pyodbc repositories were extended instead. Raise this if platform direction
changes.
