# 04 — Cycle & Refresh Data Flow (Procurement Workspace)

Scope: the actual implementation of "Cycle" and "Refresh" in
`backend/modules/procurement/`, how it touches `backend/modules/legacy_order/`,
and what a Legacy-Order-centric consolidation would inherit or have to rework.
Read-only investigation; no code/DB changes made. Tags: VERIFIED (read the
code directly), PARTIAL (saw part of the picture, inference fills a gap),
INFERRED (reasoned from adjacent evidence, not directly observed),
UNKNOWN (flagged, not resolved).

---

## 1. What "Cycle" and "Refresh" actually are

**VERIFIED** — `backend/modules/procurement/README.md:3-5` states the
lifecycle: `Business Cycle -> Refresh -> Decision Engine (VPL) -> Purchase
Manager review -> Supplier Assignment -> Export -> GRN reconciliation ->
Pending -> Next Refresh -> Cycle close.`

- **Cycle** (`procurement.procurement_cycles`) — a store-scoped header with a
  GRN/Sale-Bill boundary window (`start_grn_number`, `start_sale_bill_number`,
  `end_grn_number`, `end_sale_bill_number`), a `status` (`ACTIVE` / `Closed`),
  and an `active_refresh_id` pointer. One ACTIVE cycle per store, enforced
  (§6). VERIFIED: `backend/modules/procurement/repository.py:1-11`,
  `:206-226` (`active_cycle_exists`).
- **Refresh** (`procurement.procurement_refreshes`) — an immutable snapshot
  *inside* a cycle: parameters (`rolling_days`, `min_days`, `max_days`), a
  sequential `refresh_no` restarting at 1 per cycle, a `snapshot_status`
  lifecycle (`Draft -> Refreshing -> Ready` / `Archived` / `Closed`), and
  pointers (`previous_refresh_id`, `cycle_id`). VERIFIED:
  `backend/modules/procurement/vpl_repository.py:49-59`,
  `backend/modules/procurement/orchestration_service.py:147-224`.

Server-authoritative naming: `"<Store Code> - <YYYY-MM-DD> - Cycle"` /
`"... - Refresh <No>"` — VERIFIED
`backend/modules/procurement/orchestration_service.py:41-70`.

---

## 2. Cycle creation / execution

**VERIFIED** `orchestration_service.create_business_cycle`
(`orchestration_service.py:77-117`):
- Requires `created_by` (RBAC seam, not yet wired to a real permission check —
  comment at `:86-90`).
- Requires `store_id`; validates the store exists
  (`StoreRepository().get_by_id`).
- Rejects if an ACTIVE cycle already exists for that store
  (`cycle_repo.active_cycle_exists`, `:104-108`) — **this is the only
  concurrency guard in the whole Cycle/Refresh system that is actually
  enforced** (see §11).
- Sets `status = "ACTIVE"`, server-generates the name, inserts via
  `repository.create_cycle` (`repository.py:29-65`).

A single-screen shortcut, `ensure_active_context`
(`orchestration_service.py:372-413`), does get-or-create for both cycle and
refresh in one call — used by "the buyer picks a store and lands directly in
the workspace" (comment at `:373-383`). It does **not** force a new refresh if
one already exists.

## 3. Refresh initiation / scheduling / status tracking / completion

**VERIFIED** `orchestration_service.create_refresh`
(`orchestration_service.py:147-362`) — the real orchestration, called from:
  - the web Cycle & Refresh Console
    (`frontend/src/pages/procurement/CycleRefreshConsolePage.tsx:571-573`,
    via `POST /cycles/{cycle_id}/refreshes`), and
  - `pipeline_service.run()` (`pipeline_service.py:83-91`), used by Product
    Intelligence's `refresh_and_build` (`intelligence_service.py:611-644`).

Steps, in order (all VERIFIED against `orchestration_service.py`):
1. Validate the cycle exists and is `ACTIVE` (`:153-159`).
2. Validate decision parameters (`:161-163`, raises 400 on bad `min/max_days`).
3. Idempotency check — **feature-gated OFF by default**
   (`PROCUREMENT_REFRESH_IDEMPOTENCY`, `:172-181`; migration
   `0029_refresh_idempotency_key.sql` "NOT APPLIED" per code comment
   `:165-171`).
4. Resolve `previous_refresh_id` (either client-supplied or the cycle's
   current `active_refresh_id`, `:183-186`).
5. Insert the Refresh header as `Draft` via `vpl_repository.create_vpl`
   (`:193-209`, `vpl_repository.py:86-159`).
6. Run the Decision Engine — `decision_service.generate_vpl` (`:245`, see §4
   below); on failure, calls `_abandon()` (`:230-241`) which soft-deletes the
   half-built refresh and repoints the cycle back at the previous refresh
   (`vpl_repository.abandon_refresh`, `:293-329`).
7. (Flag-gated OFF by default, `PROCUREMENT_VPL_HISTORY`) snapshot the
   *previous* refresh's working items + assignments into history tables
   before they're cleared (`:252-294`; migration `0030` "NOT APPLIED").
8. Clear + regenerate working order items for the *new* refresh
   (`items_repo.clear_working_items` / `generate_working_items`,
   `order_items_repository.py:16-56`).
9. Carry forward still-active skips from the previous refresh
   (`carry_forward_skips`, `order_items_repository.py:59-103`).
10. Carry forward comparison/pending state (`comparison_service.carry_forward`,
    called at `:303-308` — not read in depth; out of this doc's scope).
11. Commit the whole step 8-10 transaction (`:309`); on any exception, rollback
    + `_abandon()` (`:310-313`).
12. Archive the previous refresh (`snapshot_status = 'Archived'`) unless it was
    explicitly `Closed` by the user (`:319-324`).
13. Fire Network Movement Intelligence recompute on a **daemon background
    thread**, explicitly non-blocking and allowed to fail silently
    (`:332-350`) — informational only, never touches the VPL.

**Completion tracking**: `procurement_refreshes.generation_started_at` /
`generation_completed_at` / `generated_product_count`, stamped by
`decision_repository.mark_generating` (`decision_repository.py:261-273`) and
`decision_repository.finalize` (`:322-344`) inside `decision_service.generate_vpl`.

## 4. The Decision Engine (what actually runs during a Refresh)

**VERIFIED** `decision_service.generate_vpl` (`decision_service.py:83-154`),
staged 0-6 per its own docstring (`:1-16`):
- Stage 0: load + validate `DecisionParameters` (`_load_parameters`, `:66-80`).
- Stage 1: `decision_repository.load_source` — ONE bulk SQL read, no N+1
  (`decision_repository.py:57-254`). Reads `sync.Products`,
  `sync.ProductSaleInformation`, `sync.PurchaseTrans`, `sync.ProductTrans`
  (see §9 for the exact table list and §10 for the legacy-parity CTEs).
- Stages 2-9 (collapsed into one loop, `:109-118`): for each source row, either
  `legacy_order_parity.evaluate_for_vpl` (**default** — see §5) or
  `decision_rules.evaluate` (the original Nexora engine, explicit rollback via
  `PROCUREMENT_GENERATION_PROFILE=nexora`).
- Stage 5: `decision_repository.clear_products` + `bulk_insert_products`
  (single `fast_executemany`, `:305-319`) — the VPL now holds **only**
  procurement-eligible rows (`decision_service.py:138`, confirming the user's
  memory hint "VPL persists ONLY procurement-eligible products").
- Stage 6: `decision_repository.finalize` — sets `snapshot_status='Ready'`
  and points the Cycle's `active_refresh_id` at this refresh
  (`decision_repository.py:322-344`).

Everything after Stage 0 runs inside **one transaction**
(`decision_service.py:12`, `conn.commit()`/`conn.rollback()` at `:125-131`) —
so a Refresh's VPL generation is atomic (all rows or none), independent of the
cycle-level atomicity described in §3.

## 5. `legacy_order_parity.py` — the actual bridge (D3/parity work)

**VERIFIED** `backend/modules/procurement/legacy_order_parity.py` is a
line-by-line Python transcription of the VB.NET `order_local.sql` /
`order_remote.sql` / `order_warehouse.sql` queries plus the "Additional Row"
zeroing from `order_process.insert_data_into_destination`
(docstring, `:1-17`). It is **not** calling SQL Server itself — it is a pure
function over rows that `decision_repository.load_source` already fetched
with legacy-matching CTEs (`leg_sales`, `leg_agg`, `leg_max`, `leg_wm` in
`decision_repository.py:154-198`).

Key points:
- `generation_profile()` (`legacy_order_parity.py:34-37`) defaults to
  `PROFILE_LEGACY_LOCAL` — i.e., **by default, the Procurement decision
  engine already reproduces the Legacy Order "local" math exactly**, not the
  original Nexora `decision_rules.evaluate`. Switching back to the native
  engine requires `PROCUREMENT_GENERATION_PROFILE=nexora`
  (`decision_service.py:93-97`).
- `bound_recency_days()` (`:40-47`) mirrors the legacy job's `@recencydays`
  env default of 15 — and `decision_service.py:94-97` explicitly overrides the
  Nexora engine's historical recency default of 10 with this legacy value
  whenever the legacy profile is active.
- `min_qty` / `max_qty` / `_unit_ratio` / `_sql_packs` / `buyer_result`
  (`:58-197`) reproduce the legacy min/max-qty CASE expressions, the
  mode-specific (`local`/`remote`/`warehouse`) SaleUnit division rules
  (including the documented legacy bug where `order_remote.sql` has no
  `NULLIF` and divides by zero on `SaleUnit = 0`, `:83-98`, `:101-117`), and
  the Additional-Row-zeroed buyer-visible-vs-SQL-inserted quantity distinction
  (`:120-186`).
- `evaluate_for_vpl` (`:200-267`) is the actual seam called from
  `decision_service.py:115`; it returns the same field shape
  `decision_rules.evaluate` would, so the VPL table and everything downstream
  (working items, PM review, assignment, export) is unaware which profile
  produced the row.

**This file is the single clearest piece of evidence that Procurement's
Refresh pipeline is ALREADY functionally equivalent to Legacy Order's own
order-generation SQL** — not merely "ported legacy eligibility rules" (as the
user's memory hint about `legacy_order_parity.py` says) but the full
quantity-calculation engine, selected as the *default*, with the original
Nexora engine demoted to an explicit opt-out rollback.

Important caveat stated in the file itself (`:14-16`): "Confirmed supplier
pending, in-transit, and reserved quantities do not appear in any of the
three order queries. They are not subtracted here" — so this parity profile
deliberately drops the pending/in-transit refinements the native
`decision_rules.evaluate` engine has (`pending_purchase_qty`,
`pending_sales_qty` are hard-coded to `0` at `evaluate_for_vpl:244-245`).

## 6. Cycle/Refresh ↔ Legacy Order: who calls whom

**VERIFIED one-directional dependency, Procurement → Legacy Order, never the
reverse:**

| Caller (procurement) | Callee (legacy_order) | Purpose | Evidence |
|---|---|---|---|
| `abnormal_sales_repository.py:15` | `modules.legacy_order.database` | branch DB connection string | grep hit |
| `distribution_service.py:472` | `modules.legacy_order.service.start_sync` | **blocks until the OrderNMC→NEXORA_PLATFORM sync for the source store completes**, before an export runs | `distribution_service.py:465-482` |
| `distribution_service.py:155` | `modules.legacy_order.repository` | mirrors `replace_supplier_stock` exactly (comment `:292`) | grep hit |
| `distribution_providers.py:8` | `modules.legacy_order.database.branch_connection_string` | same connection helper | grep hit |
| `reports/repository.py:40` | `modules.legacy_order.repository.branch_stock()` | "already-proven" rack/SubLocation-aware branch stock read (comment `:10,19,35`) | grep hit |

`backend/modules/legacy_order/*.py` has **zero** imports of
`modules.procurement.*` (VERIFIED — `grep "from modules.procurement"` across
the whole `legacy_order` package returned no matches). Legacy Order is
therefore fully standalone and procurement is the dependent side.

**`distribution_service._sync_source_store`** (`distribution_service.py:465-482`)
is the one REAL, wired integration point: before certain supplier exports it
calls `legacy_service.start_sync(source_store_code)` and polls
`legacy_service.get_job(job_id)` until `completed`, raising if it doesn't
finish. This drives `sync_engine.TABLE_PLAN`
(`backend/modules/legacy_order/sync_engine.py:36-46`: `Products`,
`SaleInformation`, `ProductTrans`, plus three more rows — see Part 1 of the
Legacy Order investigation for the full plan) — i.e., **the actual
OrderNMC→NEXORA_PLATFORM sync engine lives in `legacy_order`, and Procurement
reuses it rather than duplicating it.**

By contrast, `reconciliation_service._trigger_store_sync`
(`reconciliation_service.py:22-29`) — the seam used by `submit_grn`/GRN
completion — is a **stub that returns `True` unconditionally**: "today it is
a no-op so reconciliation proceeds against whatever is already synced"
(`:23-28`). This is a different, NOT-wired integration seam from the one
`distribution_service` actually uses — do not conflate the two when assessing
"does refresh talk to sync."

**Answering the brief's Q5/Q6 directly:**
- **Q5 (does refresh prepare data specifically for Legacy Order?)** — NO.
  VERIFIED: `legacy_order_parity.py` runs *inside* Procurement's own Refresh
  pipeline to make Procurement's VPL match what Legacy Order would have
  produced: direction is Procurement *imitating* Legacy Order's math, not
  Procurement *feeding* Legacy Order a data product. Legacy Order's own
  `order_process.py` / `repository.py` run their own independent SQL against
  `sync.*` and never read `procurement.*` tables (confirmed no import of
  `modules.procurement` anywhere in `legacy_order`).
- **Q6 (does Legacy Order consume refreshed/procurement data at all?)** — NO,
  confirmed by the same import-direction evidence. The two engines currently
  run side by side against the same `sync.*` source tables, each with its own
  copy of the business rules (Procurement's copy in `legacy_order_parity.py`
  is a *second, maintained-in-parallel* transcription of the *same* VB.NET SQL
  Legacy Order's `order_process.py` executes directly).

## 7. Can the refresh process safely support Legacy Order without changing its rules? (Q7)

**PARTIAL / INFERRED.** Two different claims need separating:

- *"Reuse Procurement's Cycle/Refresh/VPL pipeline as the data-prep layer in
  front of Legacy Order's rules"* — **feasible with moderate risk**, because
  `legacy_order_parity.py` already encodes Legacy Order's rules faithfully
  (VERIFIED, §5) and is unit-testable in isolation (no DB I/O, pure functions).
  The real risk is in `decision_repository.load_source`'s SQL (§9) — it has
  its OWN independently-written CTEs for the legacy aggregates (`leg_sales`,
  `leg_max`, `leg_wm`) that must stay byte-for-byte consistent with whatever
  `order_process.py` / `repository.py` compute, and the very diff open in this
  working tree (§12) shows that SQL is still being actively corrected (a
  product-master duplicate-row bug, fixed mid-investigation). This is an
  ongoing parity-maintenance burden, not a solved problem.
- *"Keep Legacy Order's own engine untouched and just let it read
  Procurement's Cycle/Refresh/snapshot tables for scheduling/history/UI"* —
  **this is NOT how it is wired today** (Q5/Q6 both NO), and would be new
  integration work, not a reuse of an existing bridge.

**UNKNOWN**: whether "safely" in the owner's sense also requires reconciling
the two engines' *rounding/edge-case* differences that already exist between
`decision_rules.evaluate` (Nexora native) and `legacy_order_parity` (legacy
transcription) — e.g. pending/in-transit quantities are zero in the legacy
profile (§5) but populated in the native one. If Legacy Order itself has no
pending-quantity concept either, this is a non-issue; that should be verified
against the Legacy Order investigation's own findings.

## 8. Which tables does Cycle update? Which does Refresh update? Which are read-only? (Q1-Q4)

**VERIFIED**, consolidated from `repository.py`, `vpl_repository.py`,
`decision_repository.py`, `order_items_repository.py`:

| Table | Written by Cycle ops | Written by Refresh/Decision-Engine ops | Read-only source |
|---|---|---|---|
| `procurement.procurement_cycles` | YES — insert (`create_cycle`), status/boundary updates (`update_cycle`, `close_cycle`, `clear_all_pending`'s caller), `active_refresh_id` repoint (`finalize`, `abandon_refresh`) | indirectly (its `active_refresh_id` column) | — |
| `procurement.procurement_refreshes` | — | YES — insert (`create_vpl`), status transitions `Draft→Refreshing→Ready/Archived/Closed` (`mark_generating`, `finalize`, `set_status`), soft-delete (`abandon_refresh`) | — |
| `procurement.procurement_virtual_products` (VPL) | — | YES — `clear_products` + `bulk_insert_products` every generation (full rebuild, not incremental) | — |
| `procurement.procurement_order_items` (Working Items) | pending-clear on cycle close (`clear_all_pending`) | YES — `clear_working_items` + `generate_working_items` + `carry_forward_skips` | — |
| `procurement.procurement_order_item_assignments` | read for `cycle_close_blockers` | written later by Assignment stage (not part of Refresh itself) | — |
| `procurement.vpl_history_batch` / `vpl_history_line` / `vpl_history_assignment` | — | YES, but **only** when `PROCUREMENT_VPL_HISTORY=1` (off by default) | — |
| `procurement.vpl_removed_line` | — | written by manual-review flows, not by Refresh itself (`upsert_removed_line`/`restore_removed_line`, not called from `orchestration_service.py`) | — |
| `sync.Products`, `sync.ProductSaleInformation`, `sync.PurchaseTrans`, `sync.ProductTrans` | — | — | **READ ONLY** — `decision_repository.load_source`, never written by Procurement |
| `sync.SupplierProductMatch`, `sync.OrderSuppliers`, etc. (legacy_order sync targets) | — | — | **READ ONLY** by Procurement; **WRITTEN** by `legacy_order.sync_engine` (owned by Legacy Order, invoked by Procurement via `distribution_service._sync_source_store`, §6) |

**Q3 answer**: `sync.*` tables (Products, ProductSaleInformation,
PurchaseTrans, ProductTrans, SupplierProductMatch, etc.) are read-only from
Procurement's side; they are written exclusively by the sync engine in
`legacy_order/sync_engine.py` (or the Store Agent pipeline it drives).

**Q4 answer (tables created/populated by background processes)**:
- `procurement.network_movement_*` (exact table name not re-verified in this
  pass — PARTIAL, see `network_movement_repository.replace_all`,
  `network_movement_service.py:230`) — populated by a **background daemon
  thread** fired at the end of every `create_refresh`
  (`orchestration_service.py:341-350`), tenant-wide, coalesced by an in-process
  lock (`network_movement_service.py:42-54`, `_lock_for`/`refresh_network_movement`
  at `:180-197`) so overlapping refreshes from different stores in the same
  tenant collapse into "one run at a time, a skipped run is harmless"
  (comment `:43-47`).
- `procurement_intelligence_cache` family (build/header/store/cache rows — see
  `intelligence_repository.save_build`, not read line-by-line in this pass) —
  populated by `intelligence_service.build_intelligence`
  (`intelligence_service.py:148-404`), triggered explicitly from the UI
  (`CycleRefreshConsolePage.tsx:596-609`, `consolidate()`), NOT automatically
  after every refresh — it is a separate, buyer-initiated step after a batch
  of refreshes completes.

## 9. Full Stage-1 source-table list (Decision Engine load_source)

**VERIFIED**, `decision_repository.py:57-254`:

| Step | Input | Source table | Processing | Destination | Output | Dependency |
|---|---|---|---|---|---|---|
| 1a | tenant_id, store_id, rolling cutoff | `sync.ProductSaleInformation` | CTE `sales`/`per_day`/`per_bill`/`agg`/`md`/`mb`/`ml` — window sales qty, max day, max bill, max single-line qty, billing frequency (Nexora-native metrics) | in-memory rowset | `window_sales_qty`, `max_day_sale_qty`, `max_bill_qty`, `max_line_sale_qty`, `billing_frequency` | none |
| 1b | tenant_id, store_id | `sync.ProductSaleInformation` | CTE `ls` — MAX(TransactionDate) full history, valid retail lines only | in-memory | `last_sale_date` | none |
| 1c | tenant_id, store_id | `sync.PurchaseTrans` | CTE `grn` — MAX(grndate) per product | in-memory | `last_received_date` | none |
| 1d | tenant_id, store_id, 90-day legacy cutoff | `sync.ProductSaleInformation` JOIN `sync.Products` (active only) | CTE `leg_sales`/`leg_agg` — legacy `order_local.sql` SalesQuantity + line frequency (`COUNT(DISTINCT ID)`) | in-memory | `legacy_window_sales_qty`, `legacy_line_frequency` | none |
| 1e | tenant_id, store_id, 90-day legacy cutoff | `sync.ProductSaleInformation` | CTE `leg_max` — legacy MaxSalesQty (no qty>0/DontConsider filter) | in-memory | `legacy_max_line_qty` | none |
| 1f | tenant_id, store_id, legacy recency window | `sync.ProductTrans` | CTE `leg_wm` — legacy recency/GRN watermark from monthly `LastBillDate`/`LastGrnDate` | in-memory | `legacy_last_sale_date`, `legacy_last_received_date` | none |
| 1g | tenant_id, store_id | `sync.Products` (de-duplicated via `ROW_NUMBER()` partition, see §12) | base product master, active only | in-memory | `product_code`, `product_name`, `unit`, `sale_unit`, `total_stock`, store-stock expr | none |
| 2 | merged source rows | n/a (Python) | `legacy_order_parity.evaluate_for_vpl` or `decision_rules.evaluate` | n/a | per-row decision fields | Stage 1 complete |
| 3 | included rows (`procurement_action == INCLUDE`) | n/a | bulk insert | `procurement.procurement_virtual_products` | VPL snapshot | Stage 2 |
| 4 | VPL rows with `suggested_qty > 0` | `procurement.procurement_virtual_products` | `INSERT…SELECT` | `procurement.procurement_order_items` | Working Items | Stage 3 |
| 5 | previous refresh's still-active skips | `procurement.procurement_order_items` (self-join) + `sync.ProductSaleInformation` (existence check) | `carry_forward_skips` | `procurement.procurement_order_items` | re-suppressed rows | Stage 4 |
| 6 | header | n/a | `finalize` | `procurement.procurement_refreshes`, `procurement.procurement_cycles` | `Ready` status, `active_refresh_id` | Stage 3 commit |

## 10. Incremental vs full refresh (Q: incremental vs full)

**VERIFIED**: the live orchestration path (`decision_service.generate_vpl`,
`orchestration_service.create_refresh`) is **always a full regenerate** —
`decision_repository.clear_products` deletes every existing VPL row for the
refresh before `bulk_insert_products` writes the new set
(`decision_repository.py:276-286`, `:305-319`), and
`order_items_repository.clear_working_items` does the same for working items
(`order_items_repository.py:16-26`) before `generate_working_items` rebuilds
them.

A **separate, earlier-looking "changed only" incremental path exists and is
still routed** (`snapshot_service.py`, mounted via `snapshot_router.py` per
`router.py:19,54`): `refresh_vpl(..., changed_only=True)` and
`refresh_product(...)` (`snapshot_service.py:40-143`) operate on
`procurement.procurement_virtual_products` directly via a different
repository (`snapshot_repository`), independent of
`decision_repository`/`decision_service`. **PARTIAL/INFERRED**: this looks
like a Sprint-3-era prototype for incremental refresh that predates (or runs
parallel to) the Stage-0-6 Decision Engine described in §4-5; nothing in
`orchestration_service.py` calls into `snapshot_service.py`, so it is not part
of the live Cycle→Refresh flow triggered from the Console. Whether it is still
used by any UI needs to be checked against `frontend`/desktop call sites if
this becomes relevant to the consolidation decision — not traced further in
this pass (UNKNOWN which, if any, screen calls `POST /vpl/{id}/snapshot/refresh`).

## 11. Concurrent refresh handling / overlap prevention

**VERIFIED gap**: `repository.refreshing_in_progress(tenant_id, cycle_id)`
is defined (`repository.py:272-287`, checks for a `procurement_refreshes` row
with `snapshot_status = 'Refreshing'`) but **grep across the entire
`backend/modules/procurement` package shows it is never called anywhere** —
`orchestration_service.create_refresh` does **not** call it before starting a
new refresh. The only real guard against overlap is:
- **Cycle level**: `active_cycle_exists` blocks opening a second ACTIVE cycle
  for the same store (`repository.py:206-226`, enforced in
  `orchestration_service.create_business_cycle:104-108`).
- **Cycle-close level**: `cycle_close_blockers` checks `active_refreshes`
  (same `'Refreshing'` status query) and the orchestration layer refuses to
  close a cycle while one is mid-generation (`orchestration_service.py:458-465`).
- **Refresh-creation level**: NO check. Two concurrent `create_refresh` calls
  against the same cycle (e.g. a user double-clicking "Run" in
  `CycleRefreshConsolePage`, or a retry racing a still-running first attempt)
  are only prevented client-side by disabling the Run button while
  `running` is true (`CycleRefreshConsolePage.tsx` state machine, `running`
  gates every action button) — there is no server-side lock. This matches the
  idempotency-key mechanism (§3 step 3) being explicitly designed for *retry*
  dedup, not concurrent-request dedup, and even that is off by default.
- **Network Movement side-effect**: DOES have a real per-tenant
  non-blocking lock (`network_movement_service.py:42-54`, §8) — this is the
  one place genuine overlap-coalescing exists, and it is scoped to the
  informational cache, not the VPL/Cycle/Refresh tables themselves.

**Answering Q11 directly**: Yes, two refreshes for the *same cycle* can
overlap today — nothing server-side stops it; the dead `refreshing_in_progress`
helper shows this was anticipated but the call site was never wired in.
Multi-store batches (different cycles, different stores) are expected to run
concurrently by design (`CycleRefreshConsolePage.runBatch`,
`Promise.allSettled` over all selected stores) and that is safe because each
store has its own cycle/refresh rows.

## 12. Partial failure / recovery behavior (Q10)

**VERIFIED**: `orchestration_service.create_refresh` has two independent
failure-recovery layers:
1. **Decision Engine failure** (`decision_service.generate_vpl` raises) —
   caught at `:246-248`, calls `_abandon()` which soft-deletes the half-built
   refresh row and repoints the cycle's `active_refresh_id` back to
   `previous_refresh_id` **only if** the cycle still points at the abandoned
   refresh (`vpl_repository.abandon_refresh:293-329`, the `AND
   active_refresh_id = ?` guard at `:320` prevents clobbering a cycle that
   something else already repointed).
2. **Working-items/history/carry-forward failure** (the `conn` transaction at
   `:266-315`) — caught at `:310-313`, rolls back that transaction AND calls
   `_abandon()` again (same soft-delete + repoint).

Both `_abandon()` calls themselves catch and merely log
(`logger.exception`, `:236-240`) rather than re-raise — so if the abandon
itself fails (e.g. DB connection lost twice), the system is left with a
`Draft`/partially-deleted refresh and a cycle pointer in an **undefined
state**; this is a real but narrow gap (PARTIAL — not reproduced, inferred
from the exception-swallowing in `_abandon`).

The VPL/working-items step (`decision_service.generate_vpl`'s own internal
transaction, §4) is independently atomic — a mid-generation SQL error there
rolls back cleanly within Stage 0-6 before `create_refresh`'s outer logic even
sees it, so the two layers compose correctly for the common case.

**Mid-generation state is visible**: `snapshot_status='Refreshing'` is set
(and committed, since `mark_generating` runs on the generation's own
connection before the bulk insert, `decision_repository.py:261-273`) at the
very start, so a crash between `mark_generating` and `finalize` would leave a
refresh stuck in `'Refreshing'` — and because nothing else transitions it out
of that state automatically, this is the exact state
`refreshing_in_progress`/`cycle_close_blockers` are designed to detect
(**but, per §11, only `cycle_close_blockers` is actually wired** — a stuck
`'Refreshing'` row blocks cycle close but does not block a fresh
`create_refresh` attempt on the same cycle).

## 13. Refresh history retention (Q12)

**VERIFIED, feature-gated OFF**: the only durable "previous refresh's working
set" history mechanism is `vpl_history_repository.write_history_batch`
(`vpl_history_repository.py:21-90`), called from `create_refresh` **only when**
`PROCUREMENT_VPL_HISTORY=1` (`orchestration_service.py:264-294`) — migration
`0030_vpl_history_persistence.sql` is marked "NOT APPLIED" in the code comment
(`vpl_history_repository.py:5`). When enabled, it snapshots the previous
refresh's order items + their assignments into
`vpl_history_batch`/`vpl_history_line`/`vpl_history_assignment`, retry-safe via
a unique index on `(tenant_id, source_refresh_id, successor_refresh_id)`
(docstring `:32-35`).

Absent that flag, the only "history" is the **soft-deleted/archived refresh
rows themselves** — `procurement_refreshes.snapshot_status` transitions to
`Archived` (never hard-deleted) when superseded (§3 step 12), and
`procurement_virtual_products`/`procurement_order_items` rows for old
refreshes are never purged by the Refresh pipeline (only `clear_products`
scoped to the *current* refresh_id is ever called) — so historical VPL/working
item data for archived refreshes remains queryable by `refresh_id`
indefinitely, just without the richer line-level/assignment-level history
schema `vpl_history_*` would add. There is a second, distinct in-memory-era
prototype (`vpl_history.py`, "Cursor-owned, in-memory prototype" per
`vpl_history_repository.py:6-8`) explicitly NOT touched by the new module —
**UNKNOWN** whether that older `vpl_history.py` + its router
(`vpl_history_router.py`, mounted at `router.py:28,47`) is still live/used by
any UI; not traced further in this pass.

## 14. Does order generation verify refresh completion before running? (Q9)

**VERIFIED, indirectly**: there is no separate "order generation" step inside
Procurement distinct from Refresh — the Decision Engine generation and
Working Item generation ARE the "order generation" (producing
`suggested_qty`/`final_qty` rows a buyer then assigns suppliers to). Within a
single `create_refresh` call, step ordering (§3) guarantees the Decision
Engine (`decision_service.generate_vpl`) fully completes and commits
(`snapshot_status='Ready'`) before working items are generated from the VPL
(`items_repo.generate_working_items` reads `procurement_virtual_products`
with `WHERE vp.suggested_qty > 0`, `order_items_repository.py:49-52`) — so
within one refresh run, completion IS verified by construction (sequential,
same code path, same outer transaction for the working-items step).

What is **not** verified is a *second*, independent caller trying to generate
working items against a `refresh_id` that is still `'Refreshing'` or
`'Draft'` from a different, concurrent request — ties back to §11's gap (no
server-side lock prevents this race).

---

## 15. Uncommitted working-tree changes (context, read via `git diff`, not modified)

Both files are mid-fix, read via `git diff` only (not staged/reverted):

- **`decision_repository.py`** (`load_source`) — wraps the `sync.Products`
  base read in a `ROW_NUMBER() OVER (PARTITION BY store_id, ProductCode)`
  subquery filtered to `product_master_row = 1`. This fixes a **duplicate
  product-master row** bug: if `sync.Products` ever contains more than one
  live row for the same `(store_id, ProductCode)` (a sync artifact, not two
  real medicines), the old plain join would silently fan out every join
  against `agg`/`md`/`mb`/etc. and double-count a product's VPL row. Directly
  relevant to the consolidation plan: any merged engine inheriting this SQL
  needs this same de-dup guard, and **should check whether Legacy Order's own
  `order_process.py`/`repository.py` SQL has (or needs) the equivalent
  guard** — this was being actively discovered/fixed here, so it's reasonable
  to assume Legacy Order's hand-written SQL could have the same latent
  exposure if `sync.Products` can legitimately hold duplicate rows per store
  (UNKNOWN whether it already guards against this — out of this doc's module
  scope, flag for the Legacy Order investigation).
- **`workspace_repository.py`** (`list_items`/`get_summary`, the PM grid
  queries — not the Refresh/Decision-Engine path itself) — adds a
  `_PRODUCT_KEY`/`_PRODUCT_RANK` de-duplication layer so the **working-items
  grid** (not the VPL) shows one row per `(store_id, product_code)` even when
  `procurement_order_items` has more than one live row for the same product
  (picks the already-assigned row, else the larger `final_qty`, else the
  larger `suggested_qty` — never sums quantities, per the comment at the top
  of `_PRODUCT_KEY`). Also switches the `sync.Products` join for display
  attributes (`UnitDescription`, `SaleUnit`, `ProductType`) from a plain
  `LEFT JOIN` to an `OUTER APPLY TOP 1 ... ORDER BY active-first` for the same
  duplicate-row reason. This is a PM-review-grid display fix, not a Decision
  Engine change — it does not alter `suggested_qty`/`final_qty` math, only
  which single row surfaces when duplicates exist.

Both diffs point at the same underlying root cause (duplicate
`sync.Products` rows per store/code) being hardened against in two different
layers of the pipeline simultaneously — worth flagging to whoever owns the
Legacy Order investigation and the DB-table-inventory investigation, since
it implies `sync.Products` may not be as clean a 1-row-per-product source as
assumed platform-wide.

---

## Open questions for the other two investigations

- Does Legacy Order's own `order_process.py` / `repository.py` SQL already
  guard against duplicate `sync.Products` rows per `(store_id, ProductCode)`,
  or would it inherit the same bug class fixed here on 2026-11-13? (table
  inventory + Legacy Order investigations)
- Is `vpl_history.py` (the older in-memory prototype, distinct from
  `vpl_history_repository.py`) still reachable from any live UI? Not resolved
  in this pass.
- Does `snapshot_service.py`'s changed-only incremental refresh path
  (`refresh_vpl(changed_only=True)`) have any live caller, or is it dead
  Sprint-3 code co-existing with the Stage 0-6 engine? Not resolved in this
  pass — would need a frontend/desktop-wide search for
  `/vpl/{id}/snapshot/refresh` call sites.
