# Phase 2 — VPL working lines and backup history

Status: **READY_FOR_REVIEW**. Designed and tested in process memory. Migration `0027` is not applied. No SQL Server connection was opened for this phase. `decision_rules.evaluate` and `decision_repository.clear_products` are unchanged.

## What was inspected

Platform tables in `backend/nexora_platform_export.sql` and the procurement SQL migrations:

| Asked name | Found |
|---|---|
| `order_cycles` | OrderNMC `dbo.order_cycles` in `docs/sql/OrderNMC_PROD_migration.sql`. Platform equivalent is `procurement.procurement_cycles`. |
| `order_cycle_refreshes` | OrderNMC `dbo.order_cycle_refreshes`. Platform equivalent is `procurement.procurement_refreshes`. |
| `order_virtual_items` | OrderNMC `dbo.order_virtual_items`, unique `(refresh_id, product_code)`. Platform equivalent is `procurement.procurement_virtual_products`, unique `(refresh_id, product_id)`. |
| `order_items` | Platform `procurement.procurement_order_items`, unique `(refresh_id, product_id)`. This is the working line. |
| `order_item_assignments` | Platform `procurement.procurement_order_item_assignments`. |

`OrderHeaderDetails` is written by `order_process.update_order_header_details` on OrderNMC. A read-only check on 2026-10-19 found exactly the insert columns and no extras: `StoreName`, `OrderId`, `OrderNo`, `OrderDateTime`, `LastSaleBillNo`, `LastBillDateTime`, `LastGRN`, `MinDays`, `MaxDays`. `LastGRN` is `bigint`. The table had 5914 rows. It is not a NEXORA_PLATFORM table. It was not altered.

`decision_repository.clear_products` deletes `procurement_virtual_products` for one `refresh_id` before a regenerate. That is the hole a history copy has to fill. Older refresh ids remain only when generation creates a new refresh instead of reusing one.

## Lifecycle

1. The first working set is opened for `(tenant_id, store_id, cycle_id)`. A second open of the same key is rejected.
2. **SUPERSEDED 2026-10-20 (temporary-implementer pass).** Line identity inside a refresh is `product_id` when the caller supplies one; only when `product_id` is absent does identity fall back to `product_code`. `product_code` alone is never the identity when a `product_id` is present — two lines sharing a `product_code` but carrying different `product_id`s are distinct and are never merged, and a line's `product_code` may change across a refresh without losing its identity. A line with neither `product_id` nor `product_code` is rejected (`IDENTITY`). A duplicate `(product_id, product_code)`-derived key in one generation is rejected (`DUPLICATE_LINE`) and nothing is archived. The previous sentence in this step, which said the key was `product_code` alone, no longer describes `vpl_history.py`. See `_key()`/`_index()`/`_resolve_by_code()` in that file.
3. An edit requires the current `row_version`. A stale version is rejected. The edit sets `manual_override`. The router's `EditBody`/`ProductActionBody` still address a line by `product_code`; `_resolve_by_code()` resolves that to the internal identity key and raises `AMBIGUOUS` (422) if more than one live line shares that code — callers that can supply `product_id` should do so to avoid that case once a live caller exists.
4. Refresh copies the whole current working set into `vpl_history_batch` / `vpl_history_line`, then builds the next working set.
5. **SUPERSEDED 2026-10-20 (temporary-implementer pass).** A line is carried forward ("touched") when `manual_override`, `supplier_code`, or `rare_confirmed` is set. `reviewed_at` alone is no longer sufficient. The previous rule (any of `manual_override`/`reviewed_at`/`supplier_code`/`rare_confirmed`) collided with `skip_item()` in `workspace_repository.py`, which sets `reviewed_at` on every skip without setting `manual_override` — under the old rule, a plain operational skip was indistinguishable from a genuine manual edit and would have been routed into `removed_manual_review` on the next refresh if the product dropped out of generation, which is not the intended skip behavior. A line whose only touched-looking signal is `item_status == "skipped"` (`_is_skip_only()`) is explicitly excluded from "touched": it is just absent from the live set on its next refresh, recoverable only from the immutable history batch, same as any other untouched absent line — it does not enter `removed_manual_review` and a supplier assignment or manual override is never discarded by a skip. See `_touched()`/`_is_skip_only()` in `vpl_history.py`. Its `final_qty`, supplier, and rare-mover confirmation stay. The new calculation is stored only as `suggested_qty`.
6. An untouched line takes the new suggestion as `final_qty`.
7. If staging or `before_commit` fails, history is not appended and the working set is not replaced.
8. `rule_snapshot_id` on a history batch is the id that was in force for that working set. A later refresh stores a new id on the new working set and does not rewrite the old batch.
9. History list defaults to the latest 10 batches for that store. `total` still counts older batches. Nothing is deleted to enforce 10.
10. There is no retention purge.

Live `clear_products` does not call this service. Until a reviewed cutover, regenerating a refresh in Purchase Manager still deletes that refresh's virtual-product rows.

## API

All under `/api/procurement/vpl-history`. Persistence is process memory until 0027 is applied.

| Method | Path | Behavior |
|---|---|---|
| POST | `/working` | Open the first working set. |
| GET | `/working` | Read it. |
| PUT | `/working/lines` | Edit one line with `expected_version`. |
| POST | `/refresh` | Archive, then build the next set. |
| GET | `/history?limit=10` | Latest headers. Older rows remain. |
| GET | `/history/{history_id}` | Header plus lines. |

## UI plan

**UPDATE (Claude, 2026-10-19 23:45 IST): a read-only history viewer now exists.** No new route or screen — `frontend/src/components/procurement/VplHistoryPanel.tsx` is a dialog opened from a new button in the existing `PurchaseWorkspacePage.tsx` header, gated on `PROCUREMENT_ADMIN` (matching `vpl_history_router.py`'s server-side gate). It calls the real mounted `GET /vpl-history/history` and `GET /vpl-history/history/{id}` — limited to 10 headers as the API already enforces, with drill-down to an older batch's lines, exactly as planned below. It does not show `final_qty`/carried-forward markers in the live grid itself (`ProductGrid`/`WorkspaceItem` are untouched — those types have no `row_version`/`rare_confirmed`/carried-forward fields, confirming this history model is still a separate, unintegrated concept from the live working-line model). **Still true:** no route was added, and nothing calls `VplWorkspace.open_cycle`/`refresh` from the live Purchase Manager, so in practice this viewer shows an empty list for every store today — the panel states this explicitly in its empty state rather than implying the feature is fully live. See `AUTONOMOUS_WORK_CONTROL.md`'s 2026-10-19T23:45 IST entry for the full file list, test results, and the explicit "browser verification not performed" caveat (no chromium/Playwright available in this sandbox).

Original plan (superseded by the above, kept for context): no new screen in this phase. When a later phase turns this on, the existing Purchase Manager grid (`DataTable`, `PageHeader`, `FilterBar`) should show `final_qty` and a carried-forward marker. History opens in the existing drawer pattern, limited to 10 headers, with an action to load an older batch's lines. Do not add a route until generation actually calls `VplWorkspace`.

## Finding 1 — untouched line row_version

**FIXED and independently verified.** Surviving lines, touched or untouched, increment `row_version` during the same refresh commit as the history append. A write with the pre-refresh version raises `VplConflict` and does not change the line. Regression tests in `tests/test_vpl_history.py` and `tests/test_vpl_history_claude_edge.py` keep the old failure path: they still attempt the stale write and require a conflict. The old success (stale edit overwriting `final_qty`) is recorded in `PHASE_2_CLAUDE_REVIEW.md` and is not the current behavior.

## Finding 2 — touched line omitted from the next generation

**IMPLEMENTED in process memory. Conversation approval, Option A.** The approval was given in the user conversation on 2026-10-19. It was not an artifact already in these files when Claude last checked. Claude's "not found in files" note stays true for that earlier check.

Approved behavior: retain a manually touched line that is missing from the next generation in a separate manual-review section, preserve edits and audit history, and prohibit automatic assignment, export, and ordering.

`VplWorkspace.refresh` now does that:

- Products still generated follow the existing rules. Untouched survivors take the new suggestion and increment `row_version`. Touched survivors keep manual values, store the new suggestion as `suggested_qty`, set `carried_forward`, and increment `row_version`.
- A touched line absent from the new list is removed from `lines` and placed in `removed_manual_review`, section **Removed from Current Suggestions — Manual Review**. `final_qty`, supplier, review, rare-mover confirmation, and product identity are kept. `orderable` is false. Removal context (`originating_refresh_id`, `originating_cycle_id`, `removed_during_refresh_id`) is in-memory only. No new SQL column was added. 0027 was not applied.
- The removed line is not a second orderable copy. `assign_supplier`, `export_lines`, `place_order`, and `submit_to_portal` raise `NOT_ORDERABLE`. Those methods do not call live generation.
- Repeating a refresh while the product stays absent does not duplicate or erase the removed line.
- If the product is generated again, it returns to the active set under the existing touched-line contract (manual values kept, new suggestion stored as `suggested_qty`, `carried_forward`, `row_version` increments) and leaves the review collection. The removal episode stays in the immutable history batch written when it left the active set. That batch's `rule_snapshot_id` is not rewritten.
- A `before_commit` exception leaves the working set and history unchanged.
- An untouched line that is simply absent is still only in history. It is not placed in manual review.

`decision_rules.evaluate`, `decision_repository.clear_products`, and `decision_service` are not called. Live generation still deletes virtual products without this history.

## Ownership

**Repository decision, 2026-10-19.** The new procurement lifecycle is owned by `NEXORA_PLATFORM` schema `procurement`. OrderNMC remains the legacy operational source. It is not a second owner of new cycles, refreshes, snapshots, VPL lines, assignments, exports, or audit history. Legacy `order_cycles` / `order_cycle_refreshes` / `order_virtual_items` names in OrderNMC docs map to `procurement_cycles`, `procurement_refreshes`, and `procurement_virtual_products`. Do not create another `order_*` copy of those concepts. The legacy OrderNMC workflow, including `OrderHeaderDetails` inserts, stays as it is until a replacement is accepted and explicitly enabled.

Input for the new path is synchronized `sync.*` data, tenant and store scoped. `VplWorkspace` is not wired to that generation yet.

## UI status

The web entry is `frontend/src/routes/AppRouter.tsx`. Electron `desktop/supplier-stock-client` is the legacy stock client and is not this screen.

`/procurement/vpl-history` (`VplHistoryScreenPage`) is behind `PROCUREMENT_ADMIN` and a flag that defaults off: `localStorage['nexora.vplHistoryScreen']='1'` or `VITE_VPL_HISTORY_SCREEN=1`. The nav link and the Purchase Manager history button use the same flag. The screen calls only `/api/procurement/vpl-history`. It does not call live generation or `clear_products`. Stock and product name are shown as unavailable. A null quantity is unavailable, not zero. A 409 conflict asks for a reload and does not resubmit the write. Store or cycle changes clear the grid before the next response, and a late response is ignored.

Claude's read-only `VplHistoryPanel` remains inside Purchase Manager and is now behind the same flag.

## Canonical field mapping

Repository evidence only. 0027 is not applied. The in-memory service is not connected to these tables.

| Business concept | Existing table / column, or missing | Repository / service | Persistence | Tests |
|---|---|---|---|---|
| Supplier assignment | `procurement.procurement_order_item_assignments.supplier_code` and `assigned_qty` (`0005`). Not a column on `procurement_order_items`. | `assignment_repository.py` | Live assignment path already writes this table. The in-memory line copies `supplier_code` for review only. Do not treat unapplied `0027.vpl_history_line.supplier_code` as the assignment store. | In-memory Option A tests reject assign/export/order/portal. Live assignment tests were not changed. |
| Rare-mover confirmation | **Missing** on applied procurement tables. `procurement_virtual_products.reason_code` (`0006`) is a generation reason, not a confirmation. | `vpl_history.py` only | Stays in memory. No new column was added. | `test_rare_mover_confirmation_survives_refresh` |
| Review state and timestamp | `procurement_order_items.reviewed_at`, `reviewed_by` (`0007`); `item_status` (`0004`) | `order_items_repository.py` | Live skip/review path. In-memory `reviewed_at` is not written there. | In-memory refresh tests. |
| Final quantity and manual override | `procurement_order_items.final_qty`, `manual_override`, `override_reason` (`0004`) | Purchase Manager order-item updates | Live. In-memory edit is separate. | In-memory stale-version and Option A tests. |
| Removed manual-review state | **Missing** in SQL, including unapplied 0027. In-memory `removed_manual_review` only. | `vpl_history.py` | Not persisted. No migration added this pass. | `test_touched_omission_moves_to_manual_review_and_preserves_values` and the Claude edge expectation updated for Option A. |
| Audit history and row version | Live lines have `created_at` / `updated_at` / `updated_by`. `row_version` is only in unapplied 0027 on `procurement_order_items`, plus unapplied `vpl_history_batch` / `vpl_history_line`. | `vpl_history.py` in memory | Do not apply 0027. Do not connect the service. | `test_untouched_line_version_advances_so_a_stale_edit_conflicts` |

## Owner decisions (2026-10-20)

None of these are **APPROVED FOR MIGRATION**. No SQL file is authorized. The keys in section 1 below are superseded by the revised contract in the next section. The 2026-10-20 independent review verdict was **BLOCK**. The owner accepts the direction in principle. Persistence stays **BLOCKED** until that revised contract and the concurrency design are independently approved. This note is not that approval.

### 1. Supplier assignment history — APPROVED IN PRINCIPLE

Preserve every assignment in immutable child history rows, including supplier identity and assigned quantity. Multiple assignments per order item are allowed in that history. The live source stays `procurement.procurement_order_item_assignments`. Do not copy assignment data onto `procurement_order_items`.

Proposed shape, still not a migration file:

| Item | Specification |
|---|---|
| Child row | `supplier_code`, `assigned_qty`, copied at refresh from each non-deleted live assignment |
| Proposed primary key | `(history_id, source_assignment_id)` |
| Parent history-line key | `(history_id, product_code)`, the same key unapplied `0027` uses on `vpl_history_line` |
| Provenance | `tenant_id`, `store_id`, `cycle_id`, `source_refresh_id`, `source_order_item_id`, `source_assignment_id`, `copied_at` |
| Transaction | The child-row insert is in the same transaction as the history batch and history lines. A failure rolls all of them back. The copy does not update the live assignment table. |

Still unresolved, so no file is written: whether unapplied `0027` is the parent or must be replaced because its line already has a single `supplier_code` and `assigned_qty`; whether a foreign key to `vpl_history_line` is allowed before `0027` is approved; no foreign key to the live `assignment_id`, because a later soft-delete must not change history. SQL Server 2014 has no JSON type. The live service currently refuses a second active assignment (`assignment_repository.any_active_assignment`); that live rule was not changed. History must still store more than one row when more than one non-deleted assignment exists.

### 2. Rare-mover confirmation — NOT APPROVED

Do not add a column. Do not write a migration. Do not reuse `reviewed_at`, `reviewed_by`, `final_qty`, `manual_override`, or `reason_code`.

| Question | Comparison |
|---|---|
| Who owns the bit | A working-item column is visible to the next refresh. A dedicated review record keeps it off the order item but needs its own read on every refresh. |
| Who may set or clear it | Only a purchase manager confirming that a rare mover may be ordered. Generation must not set it. |
| Reset on refresh | A surviving touched line keeps the confirmation. A new untouched suggestion does not inherit it. |
| Audit | The set and clear need their own actor and time. `reviewed_at` already means a general review. |
| Working item vs review record | Working item is simpler for carry-forward. A review record avoids another flag on the orderable row. |

**Recommendation, NOT APPROVED:** a dedicated review record, not a column on `procurement_order_items`, so the orderable row does not gain a new flag before the owner accepts it. The in-memory `rare_confirmed` field stays a prototype.

### 3. Removed manual-review lines — APPROVED IN PRINCIPLE

A separate persistence model, not read by orderable-line queries. Not a SQL table in this pass.

The record keeps the original `product_code` and `product_id`, the manual `final_qty`, `manual_override`, `override_reason`, `reviewed_at`, and `reviewed_by`, the assignment child rows from decision 1, and cycle/refresh provenance (`originating_cycle_id`, `originating_refresh_id`, `removed_during_refresh_id`, `removed_at`, `removed_by`). `rare_confirmed` is included only if decision 2 is later approved.

Reappearance restores that record onto the active line under the existing touched-line rule and removes the live review copy in the same commit. The removal episode stays in the immutable history batch. There is no second orderable copy.

In-memory enforcement, already tested and left unchanged: `tests/test_vpl_history.py::test_touched_omission_moves_to_manual_review_and_preserves_values` calls `assign_supplier`, `export_lines`, `place_order`, and `submit_to_portal` on the removed product and expects `NOT_ORDERABLE`. `test_reappearance_restores_touched_line_and_keeps_removal_only_in_history` checks the restore. `tests/test_vpl_history_claude_edge.py::test_touched_line_dropped_from_next_generation_survives_only_in_history` expects the line to stay out of the active list and in `removed_manual_review`.

### 4. Concurrency — documented, not added to live writes

`workspace_repository.py` has five order-item updates. None compare a version. Each calls `_run`, which commits one statement or rolls it back. They are:

1. `set_final_qty`
2. `restore_suggested`
3. `skip_item`
4. `defer_item`
5. `restore_item`

Other live writers also update items or assignments with no version check. They are not a sixth workspace function; they are separate modules:

- `assignment_repository.insert_assignment`, `update_supplier`, `update_qty`, `soft_delete`, `recompute_order_item` (used by `assignment_service`)
- `export_service.export_refresh` through `export_repository.mark_exported`
- `reconciliation_service.submit_grn` and `reconcile` through `store_last_grn` and `apply_receipt`
- `pending_repository.adjust_pending`, `set_pending_status`, `finalize_all`

No live portal-submit writer was found outside `vpl_history.py`. `pm_router.submit_grn` is the receipt path above.

Proposed contract, not implemented on these functions: one `row_version` integer. A write must include the version the caller read and use `WHERE row_version = ?`, then set `row_version = row_version + 1`. Zero rows means a conflict, not a silent success. Do not use `updated_at` as that token. Do not add a second version column. A refresh that replaces a working set and writes history is one transaction: if it fails, the old working set and the old history stay. Two processes can both pass a version check unless the predicate is in the `UPDATE`. The in-memory service already does this with `VplConflict` (`VERSION`) inside one process lock. That lock does not cover a second process. This pass does not change `workspace_repository.py`.

## Revised data contract (accepted in principle, persistence BLOCKED)

Verified from the SQL files, not from a live server. `procurement_order_items` is unique on `(refresh_id, product_id)`. `product_code` is nullable. `procurement_order_item_assignments` is keyed by `assignment_id` and can hold many rows per item. `procurement_cycles` is keyed by `cycle_id`. `procurement_refreshes` is keyed by `refresh_id` and already has a foreign key to `procurement_cycles`. Unapplied `0027` keys a history line by `(history_id, product_code)` and stores one `supplier_code` and `rare_confirmed`. **0027 is not the parent.** It is not applied and no replacement file is written in this pass.

Source ids are immutable historical identifiers copied at snapshot time. They are not foreign keys to live rows. A later change or delete of the live order item or assignment does not change the history row and does not fail because of a foreign key.

| Object | Key and constraints |
|---|---|
| History batch | In schema `procurement`. Foreign keys to `procurement_cycles(cycle_id)` and to `procurement_refreshes(refresh_id)` on `source_refresh_id`. Unique on `(tenant_id, source_refresh_id, successor_refresh_id)`. Also stores `store_id`. |
| History line | Primary key `(history_id, source_order_item_id)`. `product_id` and `product_code` are copied attributes, not the key. No foreign key to the live order item. Foreign key to the history batch. No supplier columns on this line. |
| Assignment child | Primary key `(history_id, source_assignment_id)`. Foreign key to the history line through `(history_id, source_order_item_id)`, not to the live assignment. Copied columns: `supplier_code`, `assigned_qty`, `assignment_status`, `tenant_id`, `store_id`, `cycle_id`, `source_refresh_id`, `source_order_item_id`, `source_assignment_id`, `copied_at`. |
| Removed line | One live representation per `(tenant_id, store_id, cycle_id, product_id)`: either an order item or one active removed row. Unique where `restored_at` is null. SQL Server 2014 allows that filtered unique index. Assignment, export, GRN, and portal queries do not read this table. |

Deletion: history rows are not deleted when the live row is deleted. An active removed row is cleared by setting `restored_at` in the same commit that writes the new order item. It is not hard-deleted in that commit, so the removal episode remains.

Transaction: the history batch, its lines, its assignment children, the working-set replacement, and any removed-row clear are one transaction. Failure rolls all of them back.

Retry: a second attempt with the same `successor_refresh_id` inserts nothing extra because of the batch uniqueness. Whether a retried `create_refresh` must reuse that id is **not decided**. `orchestration_service.create_refresh` currently allocates a new refresh number. That code was not changed.

Skips stay on `order_items_repository.carry_forward_skips`. A skipped line is not inserted into the removed collection. An omitted skip remains only in the immutable history batch. The removed table is for an absent manual override or an absent non-deleted assignment.

Reappearance writes the manual fields onto the new order item and clears the active removed row in the same commit. `comparison_service.carry_forward` already skips a product present in the new refresh (`exists_in_refresh`). The future persistence path must keep that behavior so a restored product is not inserted twice. That function was not changed.

Rare-mover confirmation persistence remains **NOT APPROVED**. No column.

Not decided, and not decided by code in this pass:

- Whether a retried `create_refresh` must reuse `successor_refresh_id`.
- Whether assignments that were soft-deleted before the snapshot belong in history.
- Whether a removed line may be edited before it reappears.
- Whether tenant-only access stays correct for this store-scoped set.

## Concurrency design (not a code change)

This review does not authorize adding `row_version` to live writes. `workspace_repository.py` was not edited.

Version ownership, one integer each, no second field:

- One `row_version` on the order item, for `set_final_qty`, `restore_suggested`, `skip_item`, `defer_item`, and `restore_item`.
- One `row_version` on the assignment, for `insert_assignment` only as the new row's starting version, and for `update_supplier`, `update_qty`, and `soft_delete`. `recompute_order_item` updates the order item, so it uses the order-item version.
- One `row_version` on the refresh, for `store_last_grn`.

Compare-and-swap is `UPDATE ... SET ..., row_version = row_version + 1 WHERE row_version = ?` in the same statement as the mutation. Zero rows: 404 if the row is gone, 409 `VERSION` if it still exists at another version. The client reloads. It does not resubmit with the newer version.

Refresh and edit: the history write and the working-set replacement are one transaction. An edit that starts before that commit must fail the version check rather than land on the replaced row.

Multiple workers: `VplWorkspace._lock` protects one process only. It does not protect another process, and it does not survive a restart. Live writers have no version predicate today, so two workers can both commit. The tests that interleave two `UPDATE ... WHERE row_version = ?` calls and expect one success and one 409 do not exist yet. They are required before persistence.

`reconciliation_service.submit_grn` still commits `store_last_grn` and then calls `reconcile` on a new connection. That split was not changed. A failure in reconcile leaves the stored GRN number committed.

## Schema proposal (not applied)

The decisions above replace the earlier "needs owner approval" wording for items 1 and 3. Item 2 remains not approved. SQL Server 2014 has no JSON type.

## API fields the screen may show

`GET /api/procurement/vpl-history/working` returns `lines` and `removed_manual_review.lines`. Each line has `product_code`, `product_id`, `suggested_qty`, `final_qty`, `manual_override`, `supplier_code`, `assigned_qty`, `rare_confirmed`, `reviewed_at`, `reason_code`, `row_version`, `carried_forward`, `orderable`, `updated_by`, `updated_at`. A removed line also has `section`, `originating_refresh_id`, `originating_cycle_id`, `removed_during_refresh_id`, `removed_at`, `removed_by`. `removed_manual_review.orderable` is false. Stock and product name are not in this payload.

`GET /history` returns batch headers only. `GET /history/{id}` returns the archived active lines from that refresh. It does not return the live removed collection. `VplHistoryPanel` reads only those history routes, so it does not show removed lines. `VplHistoryScreenPage` reads `working` and can show `removed_manual_review` when the flag is on. Neither screen is wired to live generation.

## Unresolved

- Confirmed supplier pending has no source column. It is not a history field.
- `transactionvalidity` is not mapped.
- Role 1 / Role 2 is not mapped.
- Not Supplied is not given a new status.
- Export store-default and system-default tiers are not added.
- Whether `product_id` is always present on a legacy `ProductCode` row is not assumed. **SUPERSEDED 2026-10-20:** `product_id` is now the preferred history/working-line key when supplied; `product_code` is the fallback, not the primary key, and is still copied as an attribute either way.
- Database verification of migrations 0026 and 0027: **NOT_VERIFIED**. `NEXORA_PLATFORM` was not opened. The OrderNMC `OrderHeaderDetails` read is separate evidence and is not a backup.

## 2026-10-20 — temporary-implementer pass (Claude, acting as Cursor's stand-in while Cursor was unavailable)

**This is not an independent review.** The same agent wrote this code and is reporting on it here; it does not carry a separate reviewer's signature. A genuinely independent re-read is still required before this is accepted, per the standing file-ownership rule that implementation and review stay separate roles.

**Scope actually touched:** `backend/modules/procurement/vpl_history.py` (in-memory model only), `tests/test_vpl_history_claude_edge.py` (new cases appended, existing cases untouched), this file, `PROJECT.md`, `AUTONOMOUS_WORK_CONTROL.md`. Did not touch `tests/test_vpl_history.py` (Cursor-authored, left as-is — all 21 of its existing cases pass unmodified against the reworked identity/skip logic, confirming the change is backward compatible with the existing contract). Did not touch `vpl_history_router.py`, any live write path, any migration file, `decision_rules.py`/`decision_service.py`/`decision_repository.py`, or anything under `backend/modules/legacy_order/` or the `OrderManagement`/`OrderManagementBackup` tables (explicit owner instruction mid-task). Did not open a database connection. Did not apply or write a migration.

**1. Canonical history-line identity — resolved.** Added `_key(product_id, product_code)`: returns a `("id", product_id)` key when `product_id` is present, else `("code", product_code)` when a code is present, else `None` (rejected as `IDENTITY`). `_index()` now keys on `_key()` instead of raw `product_code`. Two lines sharing a `product_code` with distinct `product_id`s are never merged or rejected as duplicates (tested). A line's `product_code` can change across a refresh without losing identity or its manual edits, because identity follows `product_id` (tested). A null `product_code` with a `product_id` present is accepted, not rejected (tested). The public/router-facing methods (`edit`, `assign_supplier`, `export_lines`, `place_order`, `submit_to_portal`) still take `product_code` from the router's Pydantic bodies — `_resolve_by_code()` resolves that to the internal key and raises a new `AMBIGUOUS` `VplError` (422 via the router's existing `_fail()`) if more than one live line shares that code. This is a real residual limitation: a caller that can only supply `product_code` cannot disambiguate two distinct products sharing a code. No router/schema change was made to add a `product_id` parameter to those four action endpoints or to `EditBody` — that is a follow-up, not done in this pass, and is listed below as remaining.

**2. Skip-versus-removal precedence — resolved.** `_is_skip_only(line)`: true when `item_status == "skipped"` and none of `manual_override`/`supplier_code`/`rare_confirmed` is set — this is exactly the shape `workspace_repository.skip_item()` produces (it sets `item_status='skipped'` and `reviewed_at=GETDATE()` but never touches `manual_override`). `_touched(line)` now returns `False` for a skip-only line regardless of `reviewed_at`, and otherwise requires `manual_override`, `supplier_code`, or `rare_confirmed` — `reviewed_at` alone is no longer sufficient on its own. Consequences, all tested:
- A bare skip that drops out of the next generation is simply absent from the live set (same as any untouched absent line) and is not placed in `removed_manual_review`. It remains recoverable only from the immutable history batch, consistent with "skips stay on `carry_forward_skips`" in the Revised data contract section above.
- A line that is both skipped and genuinely manually overridden (`manual_override=True`) still routes to `removed_manual_review` when it drops out — the skip does not erase the manual-edit signal.
- A line that is both skipped and carries a live `supplier_code` still routes to `removed_manual_review` — a supplier assignment is never silently discarded by a skip.
- No case in the existing or new test suite requires a line to appear simultaneously as an active working item and a removed-manual-review record; the `new_removed.pop(item_key, None)` / incoming-list reconciliation in `refresh()` already prevents that structurally (a key is either in `new_lines` or in `new_removed`, never both), unchanged by this pass.
- I did not find, and did not invent, a rule for what happens when a *defer* (`defer_item`, which sets `item_status='deferred'` without touching `final_qty`/`manual_override`) collides with omission from the next generation — `_touched()` does not special-case `deferred` at all, so a deferred-but-otherwise-untouched line that drops out behaves like any untouched line (history only, not manual review). This was not asked for explicitly in the task list and I am flagging it rather than guessing further: if a deferred line should be preserved in manual review the way a skip explicitly should not be, that is a new rule requiring owner sign-off, not inferred here.

**3. Regression tests added** (`tests/test_vpl_history_claude_edge.py`, 8 new cases, 29 total in the two files combined, all passing): null `product_code` with `product_id` present; two products sharing one `product_code`; `product_code` changing across a refresh under a stable `product_id`; `product_code`-based edit/action lookup still works when unambiguous; skip with `reviewed_at` but no override (must not reach manual review); skip plus manual override (must reach manual review); skip plus supplier assignment (must reach manual review); an explicit stale-`row_version` restatement. Store/cycle isolation and refresh-failure atomicity were already covered by the existing suite (`test_removed_lines_stay_inside_one_store_cycle`, `test_concurrent_refreshes_on_different_stores_do_not_interleave`, `test_failed_refresh_does_not_replace_working_or_history`, `test_failed_refresh_does_not_move_a_touched_line_into_review`) and were re-run, not duplicated.

**Commands run:**
```
backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=short
→ 29 passed

backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py tests/test_procurement_rules_auth.py tests/test_procurement_rules_registry.py tests/test_quantity_profile_t.py tests/test_procurement_formula_compare.py tests/test_procurement_decision_engine.py -q --tb=line
→ 91 passed, 2 failed (test_excluded_missing_grn_watermark, test_spike_floor_included_binding — same two pre-existing failures recorded earlier this session, confirmed again by zero diff below, not a new regression)
```
`git diff --stat` on `decision_rules.py`, `decision_repository.py`, `decision_service.py`, `workspace_repository.py`, `orchestration_service.py`, `order_items_repository.py`, `assignment_repository.py`, `assignment_service.py`, `comparison_service.py`, `reconciliation_service.py` → zero diff on all ten. No file under `backend/modules/legacy_order/` was opened for editing in this pass.

**Remaining owner decisions, unchanged by this pass:**
- Whether a retried `create_refresh` must reuse `successor_refresh_id` — `orchestration_service.create_refresh` was read, not edited; it still allocates a new refresh unconditionally on every call, and this pass does not claim retries are idempotent.
- Whether assignments soft-deleted before a snapshot belong in history.
- Whether a removed line may be edited before it reappears.
- Whether tenant-only access is correct for this store-scoped set.
- Rare-mover confirmation persistence: still **NOT APPROVED**, no column added, `rare_confirmed` stays an in-memory prototype field.
- Deferred-item-dropped-from-generation precedence (new, surfaced by this pass): not decided, not implemented as anything other than "behaves like untouched" by default.

**Known limitations of this pass:**
- `_resolve_by_code()` cannot disambiguate two live lines sharing one `product_code` for the router's existing `product_code`-only action endpoints (`assign_supplier`/`export_lines`/`place_order`/`submit_to_portal`/`edit`). It raises `AMBIGUOUS` rather than guessing. No router/schema change was made to accept `product_id` on those endpoints.
- This remains entirely in-memory. No migration, no persistence, no concurrency across processes. The Concurrency design section above (multi-worker, `row_version` on live writes) is unaffected by this pass.
- This implementer pass does not satisfy the task's own request for "an independent agent to review your changes if one is available" — none was available in this pass. Treat this section as implementation-complete-pending-independent-review, not as an accepted contract.

## 2026-10-20 (fix pass) — `_public()` null-product_code sort crash, fixed and self-tested only

**An independent review (the "Independent review of the temporary-implementer pass" section in `PHASE_2_CLAUDE_REVIEW.md`) found a real, previously undisclosed HIGH-severity defect in the pass above: `_public()` sorted lines with `key=lambda line: line["product_code"]`, which raises `TypeError` whenever a null-coded line coexists with any second line.** This section fixes that defect. **This fix pass is self-implemented and self-tested, exactly like the pass it corrects — it is not the independent re-verification the review requested, and must not be read as one.**

**Fix:** replaced the unsafe sort key with `_sorted_by_identity()` (new module-level function in `vpl_history.py`), which sorts `(identity_key, line)` pairs by `(product_code is None, product_code or "", _sort_token(identity_key))`. Null-coded lines sort after any string-coded line; two lines sharing one `product_code` (distinct `product_id`) get a deterministic order from the identity-key tiebreaker instead of crashing or depending on dict-iteration order. `_sort_token()` keeps an `("id", ...)` key from ever being compared against a `("code", ...)` key of a different Python type. Both `lines` and `removed_manual_review.lines` in `_public()` use this helper — the removed-section sort had the identical defect and is fixed the same way. No API response shape changed: the same fields are returned, only the ordering logic inside `_public()` changed.

**Regression tests added** (`tests/test_vpl_history_claude_edge.py`, 5 new cases, calling the real `open_cycle()`/`working()`/`refresh()` read path with more than one line present — not just constructing a single-line working set the way the prior pass's gap did): one null-coded line plus one string-coded line; two null-coded lines with distinct `product_id`s; two distinct `product_id`s sharing one `product_code`; repeated reads of a mixed null/duplicate-coded set asserting identical ordering across 5 reads; the same crash reproduced and fixed in `removed_manual_review`. Each test asserts the actual returned identities (`product_id`/`product_code` pairs), not merely the absence of an exception.

**Commands run:**
```
backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py -v --tb=short
→ 46 passed (41 before this fix + 5 new)

backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py tests/test_procurement_rules_auth.py tests/test_procurement_rules_registry.py tests/test_quantity_profile_t.py tests/test_procurement_formula_compare.py tests/test_procurement_decision_engine.py -q --tb=line
→ 96 passed, 2 failed (test_excluded_missing_grn_watermark, test_spike_floor_included_binding — the same two pre-existing failures recorded every prior session check, not a new regression)
```
`git diff --stat` on `decision_rules.py`, `decision_repository.py`, `decision_service.py`, `workspace_repository.py`, `orchestration_service.py`, `order_items_repository.py`, `assignment_repository.py`, `assignment_service.py`, `comparison_service.py`, `reconciliation_service.py`, `vpl_history_router.py` → zero diff on all eleven. No file under `backend/modules/legacy_order/` was opened for editing. No migration applied. No database connection opened. No supplier action triggered.

**Original crash manually reproduced before the fix, and confirmed absent after it**, by direct execution (not just by the new tests passing):
```
# before fix: TypeError: '<' not supported between instances of 'str' and 'NoneType'
# before fix: TypeError: '<' not supported between instances of 'NoneType' and 'NoneType'
# after fix: both scenarios return cleanly with deterministic ordering
```

**Still open, unchanged by this fix:**
- The `AMBIGUOUS` residual gap on code-only router lookups (unresolved, documented above).
- The undecided `defer_item`-drop precedence (unresolved, documented above).
- Rare-mover confirmation persistence: still **NOT APPROVED**.
- **Independent re-verification of this fix has not happened yet.** Per the fix task's own instruction ("have a separate reviewer independently reproduce the original crash and verify the fix; do not describe a self-review as independent"), this section is not that verification. Phase 2 stays `READY_FOR_REVIEW` and persistence stays **BLOCKED** until a genuinely separate pass reproduces the original crash against this code, confirms the fix resolves it, and checks the new tests' assertions rather than their names alone.

## 2026-10-20 (closing two independent-review conditions) — null `product_code` ambiguity, stated explicitly

The independent re-verification of the sort fix (`PHASE_2_CLAUDE_REVIEW.md`, "Independent re-verification of the null-product_code sort fix", verdict **APPROVE WITH CONDITIONS**) found that `_resolve_by_code()` treats `product_code=None` as an ordinary lookup value, and asked for this consequence to be stated explicitly rather than left implicit inside the `AMBIGUOUS` residual-gap notes above. This section is that statement, plus the matching regression test (`tests/test_vpl_history_claude_edge.py::test_two_null_coded_lines_coexist_distinct_in_removed_manual_review`). **Documentation and test only — `vpl_history.py` was not edited to close this condition; the behavior being documented already exists in the code from the prior fix pass.**

- **Multiple null-coded products can coexist.** A `product_id`-keyed line with `product_code=None` is a first-class, valid line, not a degraded case. Two or more such lines, each with a distinct `product_id`, coexist in the same working set or in `removed_manual_review` without merging, dropping, or interfering with each other's `final_qty`, `manual_override`, or `supplier_code` — confirmed in both the original fix pass and the independent re-verification, and now covered by a dedicated test for the `removed_manual_review` case specifically (the two-null-coded-lines-in-removed-review combination the independent review's condition 1 asked for).
- **A lookup by `product_code=None` cannot uniquely identify one of them.** The router-facing methods (`edit`, `assign_supplier`, `export_lines`, `place_order`, `submit_to_portal`) all take `product_code` as their only line-selector parameter. `None` is just another code value to `_resolve_by_code()` — it is matched the same way a string code is. The moment a second null-coded line exists in the same working set (active or removed), neither null-coded line can be targeted by `product_code=None`; both are indistinguishable from that one parameter alone.
- **`_resolve_by_code()` must fail closed with `AMBIGUOUS`; it must never guess.** This is already the implemented and tested behavior (`vpl_history.py:364-378`, unchanged by this pass) — confirmed again, for the null-code case specifically, by both the independent re-verification and the new regression test added for condition 1. An `AMBIGUOUS` `VplError` is raised rather than silently selecting one of the two matching lines, for every method that routes through `_resolve_by_code`, including `assign_supplier`/`export_lines`/`place_order`/`submit_to_portal` against a removed line (which would otherwise also need to resolve `NOT_ORDERABLE` first) — the new test confirms either `AMBIGUOUS` or `NOT_ORDERABLE` is raised and that no action ever reports `"accepted": True` for a removed, ambiguous line.
- **Identity-based handling should use `product_id` when available, with the `product_code` fallback only where appropriate.** This restates the existing identity rule from the "Lifecycle" section above (step 2) specifically for the null-code case: internal identity (`_key()`/`_index()`/reconciliation in `refresh()`) already uses `product_id` first and is unaffected by how many lines share `product_code=None` — the ambiguity is confined entirely to the four router-facing, `product_code`-only action methods and `edit`. A caller that can supply `product_id` is not affected by this limitation at all; it exists only for a caller restricted to `product_code`. This is the same residual gap already listed above as "not done in this pass" (adding a `product_id` parameter to those endpoints) — restated here for the null-code case so a future reader does not mistake it for a separate, newly discovered problem.

**This documentation closes condition 2 of the independent review. It does not resolve the underlying residual gap** (no router/schema change was made, consistent with this task's boundaries) — it only makes the null-code instance of that gap explicit rather than leaving it to be inferred from the general `AMBIGUOUS` note.

## Step 4 — durable persistence repository — 2026-10-21 (Claude)

Implements the schema side of the "Revised data contract" and "Concurrency design" sections above as an actual migration, since neither had a SQL file yet ("0027 is not the parent... no replacement file is written in this pass" — this section is that replacement).

**New migration `0030_vpl_history_persistence.sql`** (+verify+rollback, additive style, **NOT APPLIED**): `procurement.vpl_history_batch`, `procurement.vpl_history_line` (keyed `(history_id, source_order_item_id)`, no supplier columns, no `rare_confirmed` — per the contract above, confirmation stays on the live order item via D3c/0028, not in history), `procurement.vpl_history_assignment` (keyed `(history_id, source_assignment_id)`, FK to the history line not the live assignment), `procurement.vpl_removed_line` (filtered unique index enforcing at most one ACTIVE row per `(tenant_id, store_id, cycle_id, product_id)`). Also adds `row_version` to `procurement_order_item_assignments` and `procurement_refreshes` (the order-item column already exists in unapplied `0027`; reused, not duplicated) per the Concurrency design section's "one row_version per table" rule — not yet wired into any live compare-and-swap write, consistent with "this review does not authorize adding row_version to live writes" above.

**New repository `backend/modules/procurement/vpl_history_repository.py`** (new, Claude-owned, does not edit `vpl_history.py`/`vpl_history_router.py`): `write_history_batch` (one transaction: batch row, then each line, then each line's assignment children — a failure partway through leaves no partial batch, since nothing commits until the caller calls `conn.commit()`), `list_batches`/`get_batch_lines`/`get_line_assignments` (reads), `upsert_removed_line`/`restore_removed_line` (fails closed on a concurrent double-restore — the `UPDATE ... WHERE restored_at IS NULL` pattern means a second restorer's zero-row update returns `None` instead of acting on stale data)/`list_active_removed_lines`.

**Not done this pass, explicitly:**
- **Not wired into `orchestration_service.create_refresh` or any live route.** The real moment a prior working set needs archiving is `create_refresh`'s existing `items_repo.clear_working_items`/`generate_working_items` sequence for the *new* refresh — but note this investigation found `procurement_order_items` rows for the *previous* refresh are never deleted by that pipeline (they remain under their own `refresh_id`, simply no longer the "current" one the frontend reads) — so the literal data-loss risk `vpl_history.py`'s prototype was built against is narrower on the live `procurement_order_items` table than on the in-memory `VplWorkspace` abstraction itself. Wiring `write_history_batch` into `create_refresh` is a real follow-up task, flag-gated the same way as D3c/D5 once 0030 is applied, but was not attempted in this pass given the scope already covered in Steps 1-3 and the remaining master-prompt steps.
- Migration 0030 not applied.
- No restart-survival demonstration against a real SQL Server (would require 0030 applied + an isolated instance — `NOT_VERIFIED`, consistent with every DB-dependent claim in this document).
- Rare-mover confirmation persistence is a separate, already-complete piece this session (0028/D3c) — not duplicated here.

**Tests:** new `tests/test_vpl_history_repository.py`, 9 tests — batch/line/assignment insert ordering and parameter shape, multi-line batches, null-`product_code` handling, line-count accuracy, removed-line upsert, restore-when-none-active, restore success with preserved fields, and fail-closed concurrent double-restore. `pytest tests/test_vpl_history_repository.py -v` → **9 passed**. Broader: `pytest tests/ -q -k "procurement or vpl_history" --ignore=tests/test_table_creation_engine.py` → **191 passed, 11 failed**, same 11 pre-existing failures, no drift (182 + 9 new).

`git diff --stat` on `decision_rules.py`/`decision_repository.py`/`decision_service.py`/`vpl_history.py`/`vpl_history_router.py`/`rules_catalog.py`/`rules_resolution.py`/`rules_router.py`/`order_items_repository.py` → zero diff on all (only `orchestration_service.py` has a diff, from Step 3's D5 work).

No migration applied, no database connection opened, no external action taken.

**Self-implemented, not yet independently re-reviewed.**

## Step 4b — wired into live `create_refresh` — 2026-10-22 (Claude)

Closes the one explicitly-flagged gap from the entry above: `write_history_batch` is now called from `orchestration_service.create_refresh`, feature-gated behind a new env flag **`PROCUREMENT_VPL_HISTORY`** (default off, same pattern as D3c's `PROCUREMENT_RARE_MOVER_ENFORCEMENT` and D5's `PROCUREMENT_REFRESH_IDEMPOTENCY`). Migration 0030 is still **NOT APPLIED**; the flag stays off in every environment until it is.

**Re-confirmed before writing any code:** `order_items_repository.clear_working_items(conn, tenant_id, refresh_id)` deletes rows for the **newly-created** `refresh_id` (always zero rows, since nothing has been inserted under it yet) — it does not touch the previous refresh's rows. The previous refresh's `procurement_order_items` rows are left in the table under their own `refresh_id`, simply no longer "current." This confirms the prior entry's finding and means the history write is not racing a delete of the same rows it reads — it is capturing rows that would otherwise just sit there, unindexed by any later process, once the next refresh makes them non-current.

**Integration point chosen:** inside `create_refresh`'s existing step 3 transaction (the same `get_connection()` / `commit()` / `rollback()` block that already runs `clear_working_items` → `generate_working_items` → `carry_forward_skips` → `comparison_service.carry_forward`), immediately **before** `clear_working_items`. Reasoning: this is the one block in `create_refresh` that already owns a transaction spanning the handoff from the previous refresh's working set to the new one, so writing history here — and only committing with everything else in that same block — is what makes "failed refresh leaves no partial history" true without adding a second transaction boundary.

**What is read and written, in order, only when `previous_refresh_id` exists and differs from the new `refresh_id`:**
1. New `vpl_history_repository.list_items_for_history(conn, tenant_id, previous_refresh_id)` (new function, this pass) — reads the previous refresh's live `procurement_order_items` rows (`order_item_id, product_id, product_code, suggested_qty, final_qty, manual_override, item_status, skip_reason, reviewed_by, reviewed_at, row_version, is_manual`) on the **same connection/transaction**, so it sees the pre-delete state. `reason_code` is NOT read — it does not exist on `procurement_order_items` (only on `procurement_virtual_products`); the earlier draft of this function incorrectly assumed it did, caught before any test ran by checking migrations 0004/0007/0008 directly rather than trusting the in-memory prototype's field list. `is_manual` is mapped to `carried_forward` (the actual live meaning of that boolean on this table — a row inserted by `comparison_service.carry_forward`, not engine-generated).
2. If there are zero previous-refresh items (empty list, e.g. a refresh whose working set was already fully cleared), the whole history step is skipped — nothing to archive, and `write_history_batch` is never called with `line_count=0`.
3. Otherwise, `assignment_repository.list_by_refresh(tenant_id, previous_refresh_id)` (existing function, reused as-is — already the one-round-trip reader built to avoid the Supplier Queue's N+1) supplies the assignment-child rows, grouped into `assignments_by_order_item_id` by `order_item_id`.
4. `vpl_history_repository.write_history_batch(conn, ...)` — the existing Step 4 function, unchanged — writes the batch + lines + assignment children on the same connection. Not committed yet; the surrounding `try/finally` still calls `conn.commit()` only after `clear_working_items`/`generate_working_items`/`carry_forward_skips`/`carry_forward` all succeed, and `conn.rollback()` on any exception from any of them — so a failure anywhere in that sequence, including inside the history write itself, leaves neither a partial history batch nor a mutated working-items table.

**Retry/idempotency:** `write_history_batch`'s own unique index on `(tenant_id, source_refresh_id, successor_refresh_id)` is the retry guard (per its original docstring). `create_refresh` catches that specific violation (reusing the existing `_is_unique_violation` helper already in this file for D5) and continues rather than failing the whole refresh — this only matters if the exact same `(previous_refresh_id, refresh_id)` pair is ever submitted twice, which cannot happen through `create_refresh`'s own normal path (`refresh_id` is freshly minted by `refresh_repo.create_vpl` every call) but is kept as a defensive fail-open-on-duplicate rather than a 500, matching the posture `write_history_batch`'s docstring already specifies for its caller.

**Tenant/store isolation:** `tenant_id`/`store_id`/`cycle_id` are the same values already used for every other write in this same `create_refresh` call (not re-derived or guessed) — the history batch is scoped identically to the refresh it archives.

**Manual-review / deferred-line semantics preserved, not reinvented:** this wiring does not change `carry_forward_skips` or `comparison_service.carry_forward` — the actual live mechanisms for skip persistence and pending carry-forward — at all. It is a pure read-then-archive step layered before them; `item_status` (including `'deferred'`), `skip_reason`, `manual_override`, `reviewed_by/at` are copied into history exactly as they stood on the previous refresh's rows, with no reinterpretation. The in-memory `vpl_history.py` prototype's touched-line/removed-line merge logic (`_touched`, `_is_skip_only`, `removed_manual_review`) is a separate, still-unwired abstraction over a different (non-existent) live table shape and was intentionally not ported here — the live `procurement_order_items` table has no equivalent "merge previous row into newly-generated row" step; `generate_working_items` always inserts fresh rows from the VPL, and `carry_forward_skips`/`carry_forward` are the only existing mechanisms that copy prior state forward. Building a live `vpl_removed_line` write path was out of scope for "wire history into create_refresh" and is not claimed here.

**Does not create a second procurement-cycle or refresh owner:** no new `procurement_cycles`/`procurement_refreshes` row is created by this step; it only reads from and writes to the history tables scoped to the refresh pair already created earlier in the same `create_refresh` call.

**Feature flag default preserved:** `PROCUREMENT_VPL_HISTORY` defaults off (unset ≠ `"1"`); no test, fixture, or `.env` sets it to `1` anywhere in this change. Production configuration was not touched.

**Files changed:** `backend/modules/procurement/vpl_history_repository.py` (added `list_items_for_history`, ~20 lines), `backend/modules/procurement/orchestration_service.py` (two new imports + the gated block inside `create_refresh`, ~40 lines), `tests/test_procurement_orchestration.py` (6 new tests + mock-completeness fixes to 2 pre-existing tests, detailed below).

**Tests — new, in `tests/test_procurement_orchestration.py`:**
- `test_create_refresh_history_off_by_default` — flag unset: `vpl_history_repository.list_items_for_history` is monkeypatched to raise if called at all; proves the default-off path never touches the history module.
- `test_create_refresh_history_writes_batch_before_clearing` — flag on: asserts the exact call order `list_items_for_history → list_by_refresh → write_history_batch → clear_working_items → generate_working_items`, and that the values passed to `write_history_batch` (tenant/store/cycle/source/successor refresh ids, the lines list, and the assignments grouped by `order_item_id`) are exactly what was read.
- `test_create_refresh_history_skips_write_when_no_previous_items` — no `previous_refresh_id` (first refresh in a cycle): `list_items_for_history`/`write_history_batch` both monkeypatched to raise if called; proves the empty/first-refresh case never attempts a write.
- `test_create_refresh_history_failure_rolls_back_before_clearing` — forces `write_history_batch` to raise; asserts the exception propagates, `clear_working_items`/`generate_working_items` are never reached, and a tracking fake connection recorded `rollback()` called and `commit()` never called — direct evidence of "failed refresh leaves no partial history and no deleted working set," not an inference from the exception alone.
- `test_create_refresh_history_retry_is_idempotent_on_unique_violation` — forces `write_history_batch` to raise a duplicate-key-shaped exception; asserts `create_refresh` swallows it (via the existing `_is_unique_violation` check) and the refresh still completes through `clear_working_items`/`generate_working_items`.
- (identity/tenant-store correctness is covered by the assertions inside `test_create_refresh_history_writes_batch_before_clearing` above, not a separate test — `tenant_id="T1"`, `store_id="S1"` (from the mocked cycle), `source_refresh_id="R_PREV"`, `successor_refresh_id="R_NEW"` are all asserted explicitly.)

**Pre-existing test gaps fixed in the same file, found while adding the above (not new regressions — confirmed by `git stash` + re-run, both failed identically before this pass):** `test_create_refresh_full_pipeline` was failing against a real SQL Server connection (`StoreRepository`/`refresh_repo.next_refresh_no`/`refresh_repo.get_vpl`/`items_repo.carry_forward_skips` were never mocked, despite the test's own docstring claiming "DB-free"). Added the missing mocks (`StoreRepository` → existing `_StoreOK` stub, `next_refresh_no`, `get_vpl`, `carry_forward_skips`) — this is a drift fix to restore the test's own stated contract, not new behavior.

**Exact test run, this pass:**
```
backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_orchestration.py -v --tb=short
→ 12 passed (6 new + 6 pre-existing, including the 2 fixed)

backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_vpl_history_repository.py tests/test_procurement_phase2_alignment.py tests/test_procurement_orchestration.py tests/test_procurement_concurrency_d4_d5.py tests/test_procurement_rare_mover_guard.py -q --tb=short
→ 91 passed
```

**Broader suite note — a real finding, not a regression from this pass:** `pytest tests/ -q -k "procurement or vpl_history"` run across the *whole* matching set shows significant cross-file test pollution in the current working tree — confirmed independent of this change by `git stash`-ing every edit in this pass and re-running the identical command: **51 failed, 151 passed** on the stashed (pre-this-pass) tree, vs **10 failed, 197 passed** after this pass's changes (net improvement, not regression). Every file that fails in the combined run (`test_procurement_rare_mover_guard.py` among them) passes cleanly (15/15) when run in isolation — e.g. `pytest tests/test_procurement_rare_mover_guard.py -q` → 15 passed both before and after this pass. This means the "191 passed, 11 failed" figure recorded in the 2026-10-21 entries above is **stale relative to the current working tree** (likely from monkeypatch/module-state leakage introduced by uncommitted WIP in `pm_router.py`/`export_repository.py`/`vpl_repository.py` since that entry was written, not from this task) and should not be trusted as a live baseline without re-running it fresh. Flagging for whoever next touches the combined suite — this is outside this task's scope to fix (no file in the failing list was edited here) but is a real, reproducible drift from the last recorded number.

**git diff --stat** on `decision_rules.py`/`decision_repository.py`/`decision_service.py`/`vpl_history.py`/`vpl_history_router.py`/`rules_catalog.py`/`rules_resolution.py`/`rules_router.py` → zero diff on all (consistent with every prior entry — this pass touched only `vpl_history_repository.py` (additive function) and `orchestration_service.py` (additive block), both already Claude-owned/shared-read-only-with-prior-claim per the ownership table).

No migration applied, no database connection opened to a real server, no external action taken, no production flag changed.

**Status: implemented and tested, self-reviewed only — a genuinely separate reviewer should re-verify before this is treated as closed**, consistent with every prior authorization task in this thread.
