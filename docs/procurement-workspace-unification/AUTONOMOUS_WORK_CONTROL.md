# Autonomous work control — Procurement Workspace Unification

Shared coordination file for Cursor (coordinator/integration owner) and
Claude (parallel implementation + independent audit). Both agents read this
before starting work and refresh it before claiming a task.

**Contract:** `Procurement_Workspace_Master_Phase_Prompts.md` (root-level,
provided this session; not previously in `docs/procurement-workspace-unification/`).
**Owner decision on record (this session):** the "Confirmed business decisions"
section of that contract (90-day window, 13/18-day cover, 15-day recency,
`gross = MAX(avgDailySales×maxDays, maxBillQty, maxDayQty, avgBillQty)`,
`net = gross - Products.TotalStock - confirmedSupplierPendingQty`,
`Products.TotalStock` as the fixed stock source) is **owner-confirmed**,
superseding the "BLOCKED FOR BUSINESS DECISION" / "NO-GO" status recorded in
`00_EXECUTIVE_SUMMARY.md` and `docs/AUDIT_Legacy_Order_vs_Nexora_Purchase_Workspace_2026-10-19.md`
(both dated 2026-10-19, same day, predating this confirmation). Those two
audit docs remain correct as a historical record of what was unresolved
*before* the decision; do not re-open CONFLICT-001/002/003/004/005 as open
questions — treat the master-prompt values as the target formula.

---

## Phase status

| Phase | Status | Owner | Evidence |
|---|---|---|---|
| 0 — Golden formula fixture | **COMPLETE** (independently verified) | CURSOR (impl), CLAUDE (verify) | see below |
| 1 — Freeze profile + source contracts | **COMPLETE** | CURSOR review 2026-10-19 22:05 IST | Acceptance checklist below. Unknowns stay blocked. |
| 2 — VPL working lines and history | **READY_FOR_REVIEW** | CURSOR revised contract; persistence BLOCKED | Owner accepted direction in principle. Independent review was BLOCK. 0027 is not the parent and is NOT APPLIED. Rare-mover NOT APPROVED. DB verification **NOT_VERIFIED**. |
| 3 — Read-only mode data contracts | NOT_STARTED | — | depends on Phase 1/2 |
| 4–13 | NOT_STARTED | — | — |

### Phase 0 — independent verification (Claude, 2026-10-19)

Re-ran `backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_formula_compare.py -q`
from a clean working directory (no edits made). Result: **14 passed**, matches
`PHASE_0_STATUS.md` exactly. `tests/procurement_formula_compare.py` is a
Python transcription of `order_local.sql` + the Additional Row zeroing in
`order_process.py`, checked against the SQL/VB source text, not executed
against live SQL Server — consistent with what the status file claims (no
over-claiming found). No files under `backend/modules/procurement/` or
`frontend/` were edited for Phase 0. **Verdict: accept. Phase 0 gate passed.**

### Phase 1 — in progress, split ownership

**CURSOR's existing uncommitted work** (pre-dates this control file, found in
working tree at session start) already resolves part of Phase 1/the legacy
side in practice:
- `backend/modules/legacy_order/sql/order_local.sql`, `order_remote.sql`,
  `service.py`: recency hard-code `-10` → parameterized `@recencydays`,
  default now `LEGACY_RECENCY_DAYS` env = **15** (matches master-prompt
  "15-day valid-sale recency target").
- `order_process.py`: new `refresh_warehouse_stock()`, NMW stock bridged into
  `SupplierStock`/`SupplierProductMatch` via `product_mapping` before every
  retail order generation; IsOffer moved from per-row-per-load to a single
  set-based UPDATE at generation time (perf fix, matches audit §16/migration 0007).
- `desktop/supplier-stock-client/src/App.jsx` (+1596 lines), `repository.py`
  (+471), `order_export.py` (+190), `router.py`, `schemas.py`: not yet
  function-by-function reviewed by Claude as of this entry.
- **Tests:** `tests/test_legacy_order_workflow.py` 28/28 pass against this
  working tree (verified by Claude). `tests/test_procurement_decision_engine.py`
  has 2 pre-existing failures (`test_excluded_missing_grn_watermark`,
  `test_spike_floor_included_binding`) — confirmed via `git diff --stat HEAD`
  showing **zero** working-tree diff on `decision_rules.py` or that test file,
  so these predate current WIP and are not a regression from this phase's work.

**CLAUDE's claimed task (this entry):** Phase 1 "source data contracts for
all three modes" — read-only documentation task, no code/API changes:
- Map exact fields each of the three loaders (Qty Check / Auto Purchase
  Update / Supplier Stock Availability) needs, from `legacy_order/repository.py`
  (`LoadQtyCheckData`/`LoadDataForSupplier`/`LoadDataForSupplierStock`
  equivalents) and `decision_repository.load_source`.
- Confirm stock source, pending source, transaction-validity meaning, date
  semantics per the master prompt's "freeze profile" ask — record UNKNOWNs
  explicitly rather than guessing (`transactionvalidity` mapping, confirmed
  pending source — both already flagged UNKNOWN in the audit and in
  `PHASE_0_STATUS.md`'s "Unknowns left explicit").
- **Files to be touched:** none yet outside this control file + a new
  `docs/procurement-workspace-unification/14_PHASE1_SOURCE_CONTRACTS.md`.
  Not touching `backend/modules/legacy_order/*`, `backend/modules/procurement/*`,
  or any frontend/desktop file — those stay Cursor's.

### Task P1-B — source field map (CLAUDE, READY_FOR_REVIEW)

**Claimed and completed 2026-10-19T21:40 IST.** Deliverable:
`docs/procurement-workspace-unification/PHASE_1_SOURCE_FIELD_MAP.md`
(new file, doc-only). Maps Qty Check / Auto Purchase Update / Supplier
Stock against actual source (`repository.py:651-797,1036-1061`), with
stock source, SaleUnit/pack, pending-quantity, and `DontConsiderInOrder`
findings, all tied to file/line references. Role 1/Role 2 left explicitly
unmapped. No Python/SQL/UI/migration file edited; no production DB
queried — consistent with the task's stated constraints.

Key findings (full detail in the deliverable, not duplicated here):
- Stock source = `OrderManagement.TotalStock`, frozen at generation time,
  not live — consistent with the owner-confirmed formula's stock term,
  but it is a snapshot, not a live read.
- Pending quantity: **no source column exists** in any of the three
  loaders. Still blocked — matches the blocker already on record below.
- `DontConsiderInOrder`: line-level only, applied upstream at generation;
  no product-level flag checked by the three read loaders themselves.
  Known pre-existing gap already recorded in `PHASE_0_STATUS.md`, not new.
- `is_warehouse_stock` flag (Supplier Stock mode) confirmed as the
  existing mechanism for flagging NMW-bridged rows vs. real suppliers.

This task did not touch `backend/modules/legacy_order/router.py` to
confirm which API paths front these three functions — flagged as an
UNKNOWN for whoever starts Phase 3, since `router.py` is Cursor's active
WIP and was intentionally not opened here.

**P1-B independently re-verified by Claude against P1-A, same pass:** also
re-ran `pytest tests/test_quantity_profile_t.py tests/test_procurement_formula_compare.py -q`
→ **16 passed**, matches Cursor's P1-A report exactly. Confirmed
`git diff --stat` shows **zero** change to `decision_rules.py` and
`decision_service.py` — the live engine is genuinely unchanged, consistent
with P1-A's own claim ("not called by `decision_rules.evaluate`"). P1-A
checks out.

**P1-B status: accepted by Cursor integration review, 2026-10-19 22:05 IST.** Claude has not appended a separate sign-off after this review.

## Phase 1 acceptance review (Cursor, 2026-10-19 22:05 IST)

No files under the decision engine, SQL, UI, or production data were edited for this review. `PHASE_1_SOURCE_FIELD_MAP.md` was not rewritten.

Tests re-run:

```
backend\.venv\Scripts\python.exe -m pytest tests/test_quantity_profile_t.py tests/test_procurement_formula_compare.py -q --tb=line
→ 16 passed
```

| Criterion | Result |
|---|---|
| Approved profile documented in a tested function next to the engine | Met. `quantity_profile_t.evaluate_profile_t`. Constants 90 / 13 / 18 / 15. Same packs, reason, and auto_order as Phase 0 `target_formula` on every fixture case. |
| Live engine unchanged | Met. `decision_service.py` still calls `decision_rules.evaluate`. No import of `evaluate_profile_t` anywhere except `quantity_profile_t.py` and its tests. `rules_catalog.py` imports only the rare-mover warning string. |
| Profile selection | Reviewed. There is no store selector. Profile T runs only when called directly. Cutover is not approved. |
| Three mode contracts | Met. Re-read `repository.py`: `qty_check_rows` 1036–1061, `orders_by_supplier` history 741–781, stock 721–740, warehouse flag 792–795. Filters and columns match the source map. |
| Read endpoints identified, no new UI | Met. `GET /api/legacy-order/qty-check/{store_name}`. `GET /api/legacy-order/orders/{store_name}/by-supplier?supplier_code=&mode=history\|stock`. Router prefix `/api/legacy-order`. |
| Stock source | Met. Generation SQL selects `p.TotalStock`. `order_process.COLUMN_MAP` copies it onto `OrderManagement.TotalStock`. The three loaders read that column and do not re-read `products` or `ProductTrans`. Last-offer qty is the live exception, as the map says. |
| SaleUnit | Generation CASE yields Orderqty 0 when SaleUnit is not > 0. The three loaders do not re-check it. `makeCommitQty` (`App.jsx` 4080–4109) and `OrderWorkspacePage` export (`exportOrder`, no SaleUnit predicate) do not block 0 or null. Export writes the SaleUnit column through (`order_export.py`). |
| DontConsiderInOrder | `order_local.sql` sales CTE includes `ps.DontConsiderInOrder = 0`. The three loaders do not filter a product-level flag. Legacy can still order when the product flag is set and window qty is supplied. Profile T excludes that case. |
| Rulebook and tests reviewed | Met. `06_PROCUREMENT_RULEBOOK.md` records the approved 90/15/13/18/`TotalStock` target and still describes the legacy formula. Phase 0 table remains the test expectation. |
| No live order change in this review | Met. |

### Settled in this review

- Router paths above. The source map's fourth UNKNOWN is closed.
- SaleUnit is not blocked at qty-commit or stock export in the handlers read above. The source map's first UNKNOWN is closed. Profile T still blocks invalid SaleUnit; the live legacy path does not.

### Blockers carried forward (not guessed)

- Confirmed supplier pending: no column in the three loaders. Do not treat the missing term as zero.
- `transactionvalidity`: the sales CTE keeps `= 0`. Other values are still unmapped.
- `Transactiondate` time component: still UNKNOWN. Profile T uses the `max_day_qty` it is given.
- Role 1 / Role 2: still unmapped. Phase 12 stays blocked.

Phase 1 is **COMPLETE**. Next authorized master-prompt phase is Phase 2 (VPL working-lines and backup/history schema plan). Phase 2 has not started. Migration 0026 and `/procurement/rules` belong to the rules-registry workstream and are not that phase.

## File ownership boundaries (current)

| Path | Owner | Notes |
|---|---|---|
| `backend/modules/legacy_order/**` | CURSOR | active uncommitted WIP; do not edit |
| `desktop/supplier-stock-client/**` | CURSOR | active uncommitted WIP; do not edit |
| `frontend/src/pages/legacy-order/**` | CURSOR | active uncommitted WIP; do not edit |
| `backend/modules/procurement/quantity_profile_t.py` | CURSOR | P1-A claim 2026-10-19 21:32 IST. New file only. |
| `tests/test_quantity_profile_t.py` | CURSOR | P1-A tests. New file only. |
| `backend/modules/procurement/decision_rules.py`, `decision_service.py` | SHARED_READ_ONLY | Do not edit. Profile T and the rules registry must not call `evaluate`. |
| `backend/modules/procurement/**` other than the claimed registry files and `quantity_profile_t.py` | SHARED_READ_ONLY | Claim in this file before editing. |
| `docs/procurement-workspace-unification/14_PHASE1_SOURCE_CONTRACTS.md` | CLAUDE | P1-B. Cursor will not create or edit this file. |
| `docs/procurement-workspace-unification/PHASE_1_SOURCE_FIELD_MAP.md` | CLAUDE | Named in the resume prompt. Cursor will not create it. |
| `tests/test_procurement_formula_compare.py`, `tests/procurement_formula_compare.py` | CURSOR (author) | Claude verified, did not edit |
| `backend/modules/procurement/rules_catalog.py` | CURSOR | Rules registry catalog. New file. |
| `backend/modules/procurement/rules_resolution.py` | CURSOR | Effective-rule resolution. Not called by `decision_rules.py`. |
| `backend/modules/procurement/rules_router.py` | CURSOR | HTTP API for the registry. |
| `backend/modules/procurement/router.py` | CURSOR | Include line for `rules_router` only. Do not edit cycle handlers. |
| `backend/modules/procurement/sql/0026_procurement_rules_registry.sql` | CURSOR | Additive migration. Not applied. |
| `backend/modules/procurement/sql/0026_procurement_rules_registry_rollback.sql` | CURSOR | Rollback instructions. Not applied. |
| `backend/modules/procurement/sql/0026_procurement_rules_registry_verify.sql` | CURSOR | Verification SQL. Not applied. |
| `tests/test_procurement_rules_registry.py` | CURSOR | Catalog, validation, isolation, snapshot tests. |
| `frontend/src/pages/procurement/ProcurementRulesPage.tsx` | CURSOR | Admin route. |
| `frontend/src/routes/AppRouter.tsx` | CURSOR | One route only for this workstream. |
| `frontend/src/components/sidebar/navConfig.ts` | CURSOR | One nav entry only. |
| `docs/procurement-workspace-unification/RULES_REGISTRY_CLAUDE_REVIEW.md` | CLAUDE | Assigned. Source, schema, validation, and permission review. Cursor will not create this file. |
| `tests/test_procurement_rules_claude_review.py` | CLAUDE | Assigned. Extra isolation/permission cases only. Do not edit Cursor's registry test. |
| `docs/procurement-workspace-unification/PHASE_2_VPL_HISTORY.md` | CURSOR | Phase 2 design, mapping, API contract, UI plan. |
| `backend/modules/procurement/vpl_history.py` | CURSOR | Working-line refresh and history. Not called by `decision_rules` or `clear_products`. |
| `backend/modules/procurement/vpl_history_router.py` | CURSOR | Read/edit/refresh/history API. Process memory until 0027 is applied. |
| `backend/modules/procurement/router.py` | CURSOR | Include lines for `rules_router` and `vpl_history_router` only. |
| `backend/modules/procurement/sql/0027_vpl_history.sql` | CURSOR | Additive. Not applied. |
| `backend/modules/procurement/sql/0027_vpl_history_rollback.sql` | CURSOR | Rollback. Not applied. |
| `backend/modules/procurement/sql/0027_vpl_history_verify.sql` | CURSOR | Verification. Not applied. |
| `tests/test_vpl_history.py` | CURSOR | Snapshot, refresh, rollback, duplicates, stale edits. |
| `docs/procurement-workspace-unification/PHASE_2_CLAUDE_REVIEW.md` | CLAUDE | Assigned. Schema, keys, refresh preservation, concurrency, failure recovery. Cursor will not create this file. |
| `tests/test_vpl_history_claude_edge.py` | CLAUDE | Assigned. Extra edge cases only. Do not edit `test_vpl_history.py`. |
| `backend/modules/legacy_order/_TEMP_sample_order_data.py` | CLAUDE | Temporary. Cursor will not edit or delete it. |

## Decisions already confirmed by the user (this session)

1. Claude's role for this conversation: parallel implementer (not read-only auditor) — switches from the session's initial auditor-only framing.
2. Master-prompt "Confirmed business decisions" section is owner-approved, overriding the 2026-10-19 audits' NO-GO/BLOCKED status on the same formula questions.

## Unresolved decisions and blockers

- `transactionvalidity` mapping for cancelled/modified bills — explicitly unmapped, master prompt says do not invent it. Still blocked.
- Confirmed-supplier-pending source column — no single verified source exists in either engine today. Still blocked; Phase 1 contract work must record this as blocked per mode, not guess a column.
- Role 1/Role 2 → Admin/PM mapping — still unconfirmed, blocked per master prompt §Phase 12.
- Live SQL Server was not queried for either Phase 0 or this Phase 1 doc pass — per master-prompt safety rule 2, stop and request explicit approval before any live DB read.

## Database/migration status

Migration `0026_procurement_rules_registry.sql` is written and **not applied**.
Migration `0027_vpl_history.sql` is written and **not applied**.
Phase 2 rechecked database targets once: `backend/.env` `DB_DATABASE=NEXORA_PLATFORM` and legacy `OrderNMC` are the shared server, not an isolated test database. No connection was opened and neither script was executed.
Database verification for 0027: **NOT_VERIFIED**.
Existing `procurement_refreshes.rolling_days/min_days/max_days` stay as the
live refresh parameters. `rule_snapshot_id` is a nullable pointer added only
in the unapplied script. `OrderHeaderDetails` is not altered.

## Database availability and offline-fallback plan (Claude, 2026-10-19 21:58 IST)

**Clarified with the owner mid-task:** the host named "10.20.73" in the
offline-fallback brief does not match any configured connection string in
this repo. The real configured host is `192.168.10.73` (`backend/.env`
`DB_SERVER`), the known `.73`/`CLIENT-3\SQLEXPRESS` node from prior
sessions, serving both `NEXORA_PLATFORM` and the legacy `OrderNMC`
database. Owner confirmed treat "10.20.73" as that host. Owner also
clarified the outage window is **10:20 PM IST tonight**, not already past.

**Verified current state (21:35-21:58 IST, before the outage window):**
- `database.database_health()` (`backend/modules/legacy_order/database.py:199-234`,
  read-only, does not mutate anything) against `OrderNMC` on `192.168.10.73`:
  `reachable=True, state=ONLINE, access=MULTI_USER`. Elapsed ~0.33s.
- Direct `pyodbc.connect` against `NEXORA_PLATFORM` on the same host via
  `database.platform_connection_string()`: reachable, ~0.04s.
- **Both databases are online right now.** No outage has started. This is
  a planned future event (~22:20 IST), not a current incident — recorded
  here as the pre-outage baseline, not as a failure.

**Fallback readiness already in place, found while doing other tasks
tonight (not newly built for this entry):**
- The entire **Procurement Rules Registry** workstream
  (`rules_catalog.py`/`rules_resolution.py`/`rules_router.py`/
  `ProcurementRulesPage.tsx`) already runs on **pure in-memory process
  state** — `RulesRegistry.__init__` (`rules_resolution.py:83-88`) holds
  plain Python dicts, no `pyodbc`/DB import anywhere in that module or
  `rules_router.py`. This UI and its API are **already unaffected** by
  `.73` going offline tonight; no fallback work is needed for it.
  Confirmed by reading both files line-by-line in the review above.
- `quantity_profile_t.evaluate_profile_t` (Phase 0/P1-A) is a pure
  function over fixture inputs, also DB-independent.
- The three legacy-order loaders (Qty Check / Auto Purchase Update /
  Supplier Stock, mapped in `PHASE_1_SOURCE_FIELD_MAP.md`) **do** require
  `database.get_central_connection()` against `OrderNMC` on `.73` — these
  will go dark during the outage window. No mock/fixture layer exists for
  them yet.

**Labeling requirement for anything built against sample/offline data
tonight:** per the brief's §2, any screen or response running on sample
data instead of a live `.73` connection must be clearly labeled
`DEVELOPMENT / SAMPLE DATA` in the UI. Nothing in the current
`ProcurementRulesPage.tsx` needs this label today because it was never
reading `.73` in the first place (process-memory only) — it is not
"sample data standing in for a live DB," it is correctly described as
"not yet persisted to a database at all," which the page's own banner
text already states ("Migration 0026 is not applied... overrides live in
this API process").

**Resume behavior commitment (per brief §7):** when `.73` comes back
online after tonight's outage, no agent should auto-reconnect any
write path or treat availability alone as authorization. Re-verify
`database.database_health()` fresh and require the same explicit
authorization checks already in force before any DB-dependent write or
migration resumes. This is the same posture already documented under
"Live SQL Server was not queried... stop and request explicit approval."

## Procurement Rules Registry workstream

Status: **READY_FOR_REVIEW** for the catalog, resolver, admin route, and unapplied migration. Not complete: 0026 is not applied, snapshots are not attached by refresh generation, and Claude's source/schema review file is not written yet. This workstream does not replace `06_PROCUREMENT_RULEBOOK.md`.

Depends on: Phase 0 fixture (complete) and the owner-confirmed master-prompt
formula. Does not wait on Phase 1 being marked complete. Does not start the
workspace UI phases.

Acceptance:
- Stable rule IDs with source, current behavior, target, status, validation, override policy.
- Unknowns stay `UNVERIFIED` or `DECISION_REQUIRED`.
- Defaults and store overrides resolve deterministically; locked and blocked values are rejected.
- Changes are versioned in the registry audit log. Snapshots do not change after later edits.
- Store isolation and optimistic concurrency are tested.
- Migration is additive, with verify and rollback SQL, and is not applied here.
- Admin route reuses PageHeader, DataTable, EmptyState, ErrorState, FilterBar.
- `decision_rules.evaluate` is unchanged. Profile T stays off the live path.

Claude assignment (claim in this file before editing; do not edit Cursor-owned registry files):
- Write `RULES_REGISTRY_CLAUDE_REVIEW.md`: source-backed check of the catalog, schema/migration review, validation and permission review.
- Optional extra cases only in `tests/test_procurement_rules_claude_review.py`.
- UI acceptance review after the route exists. Record the review in the Claude file, not by editing `ProcurementRulesPage.tsx`.

**Done (Claude, 2026-10-19 22:02 IST):** `RULES_REGISTRY_CLAUDE_REVIEW.md`
written. Independently re-ran both `pytest tests/test_procurement_rules_registry.py
tests/test_quantity_profile_t.py -q` (8 passed, matches) and `npx tsc -b`
(exit 0, matches). Catalog, migration, rollback, and validation logic all
check out against source. **One real gap found and flagged for Cursor:**
`rules_router.py`'s mutating routes (`put_default` especially; also
`put_override`/`reset_override`/`create_snapshot`) have no server-side
`PROCUREMENT_ADMIN`-equivalent capability check — only
`get_current_user_optional` plus `assert_tenant_access` (tenant
*membership*, not role). The frontend route gates with
`RequireCapability cap="PROCUREMENT_ADMIN"`, but the master prompt's own
Phase 12 text says not to rely on hiding buttons — enforce server-side.
Recommend Cursor add the capability check before this workstream is
called `COMPLETE`. Did not fix it myself — registry files are Cursor-owned
per the ownership table above; raising it for Cursor's review per the
shared-ownership protocol ("stop that subtask and hand off").

## Test commands run and results (this session, Claude)

```
backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_formula_compare.py -q
→ 14 passed

backend/.venv/Scripts/python.exe -m pytest tests/test_legacy_order_workflow.py tests/test_procurement_decision_engine.py -q
→ 28 passed, 2 failed (both in test_procurement_decision_engine.py, pre-existing on HEAD, zero working-tree diff on files under test)
```

## P1-A result (Cursor, 2026-10-19 21:36 IST)

Command:

```
backend\.venv\Scripts\python.exe -m pytest tests/test_quantity_profile_t.py tests/test_procurement_formula_compare.py -q --tb=short
```

Result: **16 passed**. Pytest cache write denied (WinError 5). Not a failure.

`evaluate_profile_t` matches `target_formula` on all 14 fixture cases. It is not called by `decision_rules.evaluate`. No store-level profile switch exists yet, so the live engine is unchanged. Confirmed-pending column, `transactionvalidity`, and calendar-day vs timestamp remain UNKNOWN and are not resolved inside the function.

P1-A status: **READY_FOR_REVIEW**. Phase 1 stays IN_PROGRESS until Claude's source map exists and the phase acceptance line (source field map plus profile left off the live path) is reviewed.

## TEMP — offline-window sample data fixture (Claude, claimed 2026-10-19 22:05 IST)

**TEMPORARY. Delete this file and this section after `.73` is confirmed back
online and re-authorized for use** (per owner instruction: "tomorrow clear
all temp files and connect live db"). Not part of any phase deliverable,
not reviewed/owned by Cursor, not referenced by any production code path.

**File:** `backend/modules/legacy_order/_TEMP_sample_order_data.py` — new,
Claude-owned, temporary only.

**Purpose:** exercise the three legacy-order loaders
(`qty_check_rows`, `orders_by_supplier` history/stock) against realistic
in-memory sample rows during tonight's `.73` outage window, using the
existing `_FakeConnection`/`monkeypatch` pattern already established in
`tests/test_legacy_order_workflow.py:17-55` — no new DB, no sqlite, no
mock framework introduced. Confirms the exact column shapes documented in
`PHASE_1_SOURCE_FIELD_MAP.md` by actually running the loader functions
against sample rows shaped like `OrderManagement`/`PurchaseTrans`/
`SupplierStock`/`SupplierProductMatch`, not just reading the SQL text.

**Explicit safety properties:**
- No real/production data copied in — every value is synthetic, invented
  for this fixture, labeled `DEVELOPMENT / SAMPLE DATA` in its own docstring.
- Read-only: calls `qty_check_rows`/`orders_by_supplier` (both pure SELECT
  in production) against the fake connection; never calls
  `update_order_qty`/`assign_supplier`/`bulk_assign_rows`/any write path.
- No real supplier portal, no export, no WhatsApp/email send.
- Cannot "accidentally submit a real order" — it never imports
  `order_process.run_order_process` or any network/portal adapter.

**File ownership:** `backend/modules/legacy_order/_TEMP_sample_order_data.py`
— CLAUDE, temporary. Cursor should not build on top of this file; it does
not become part of the legacy_order module's real surface.

**Run result (Claude, 2026-10-19 22:08 IST):**
`backend/.venv/Scripts/python.exe backend/modules/legacy_order/_TEMP_sample_order_data.py`
→ ran clean, all three modes returned rows shaped exactly as documented in
`PHASE_1_SOURCE_FIELD_MAP.md`. One real bug caught by actually running it
(not just reading the SQL): `orders_by_supplier(mode="stock")` also calls
`get_store()` internally for the `is_warehouse_stock` flag
(`repository.py:792`), a second query shape (row-attribute access via
`_row_to_store`, not a plain tuple) that the simple fixture cursor didn't
support — fixed by mocking `repository.get_store` directly for that mode
rather than over-building the fake cursor. `is_warehouse_stock` confirmed
`True` when `supplier_code == store['ho_code']`, matching the documented
behavior. **Action item for tomorrow:** delete
`backend/modules/legacy_order/_TEMP_sample_order_data.py` and this whole
section once `.73` is back and re-authorized — tracked in `PROJECT.md`
under "Known temporary files to clean up."

## Phase 2 Claude review — done (2026-10-19 22:12 IST)

`PHASE_2_CLAUDE_REVIEW.md` written. Independently re-ran
`pytest tests/test_vpl_history.py -q` → 7 passed, matches. Traced
duplicate-line rejection, stale-version rejection, and the one tested
failure-injection point (`before_commit`) at the code level, not just the
test level — all three correctly leave no partial state. Migration 0027
is additive, idempotent, FK-correct, does not touch
`OrderHeaderDetails`/`OrderManagement`; rollback correctly refuses when
history exists or `row_version` has moved, and correctly finds the
default constraint by name before dropping the column.

**One real gap found, not previously flagged:** in `refresh()`, a
manually-touched working line (override/review/supplier/rare-confirmed)
whose `product_code` does **not** appear in the new `generated` list is
silently dropped from the new live working set (still preserved in
history, since the full old working set is archived verbatim — so no
data loss, but the PM's manual work stops being live/editable without any
signal). Not tested in `test_vpl_history.py`. Not necessarily wrong — the
master prompt doesn't say what should happen when a manually-assigned
product drops out of the next generation — but flagging for an explicit
decision rather than leaving it implicit.

**Database verification: NOT_VERIFIED**, consistent with the instruction —
no isolated SQL Server database was available; the existing test setup
(pure Python mocks) cannot validate real transaction atomicity, FK
enforcement, or `DECIMAL`/`DATETIME` rounding on SQL Server itself.

Did not edit any Cursor-owned file. Phase 2 stays at `READY_FOR_REVIEW`
per the acceptance rule — not advancing it to `COMPLETE` myself.

**UPDATE 2026-10-19 22:18 IST — second, more serious finding, via new
edge-case tests.** Wrote `tests/test_vpl_history_claude_edge.py` (6 new
tests, Claude-owned, does not edit `tests/test_vpl_history.py`). All 6
pass; combined with Cursor's 7, **13/13 pass**
(`pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q`).

**SEVERITY HIGH defect confirmed by running a test, not just reading
code:** an **untouched** line's `row_version` does not advance across a
refresh (`vpl_history.py:193`, incoming lines always default to
`row_version=1` since the generated payload carries no version key). A
client holding a pre-refresh `row_version=1` can submit a stale edit
*after* a refresh and it succeeds silently — no `VplConflict` — because
the post-refresh line also happens to be `row_version=1`, not because the
data is actually unchanged (`final_qty` did change). Touched lines are
correctly protected (their version IS incremented on refresh,
`vpl_history.py:118`); only untouched lines have this hole. Full
reproduction and recommended fix (increment every line's version on
refresh, or derive part of it from `refresh_id`) in
`PHASE_2_CLAUDE_REVIEW.md`'s "Additional finding" section. Not fixed here
— Cursor-owned file; handing off per the shared-ownership protocol.

**Files created this task:** `docs/procurement-workspace-unification/PHASE_2_CLAUDE_REVIEW.md`,
`tests/test_vpl_history_claude_edge.py`. No Cursor-owned file touched.

**UPDATE 2026-10-19 22:35 IST — fix independently verified.** Cursor fixed
Finding 1 in `vpl_history.py:122-124`: untouched lines that existed in
the prior working set now get `row_version = previous + 1` on refresh,
same mechanism already used for touched lines (no competing version
field). Cursor added `test_untouched_line_version_advances_so_a_stale_edit_conflicts`
to `tests/test_vpl_history.py`, reproducing the exact original failure as
a regression test. I added `test_repeated_refreshes_never_reset_or_reuse_an_untouched_lines_version`
to `tests/test_vpl_history_claude_edge.py` (point 8 of the fix spec —
monotonic versioning across repeated refreshes, not just one).

Re-ran: `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q`
→ **15 passed**. Manually confirmed version sequence `[1,2,3,4,5,6]`
across 5 repeated refreshes — strictly increasing, never repeats.
`git diff --stat` on `decision_rules.py`/`decision_repository.py`/
`decision_service.py` → zero diff, live engine untouched. Broader
procurement suite: 45 passed, 2 failed — same 2 pre-existing failures
flagged at session start, no new regression.

**Verdict: Finding 1 fix confirmed correct.** Full writeup in
`PHASE_2_CLAUDE_REVIEW.md`'s "Fix verified" subsection. **Finding 2**
(manually-touched line silently dropped when its product leaves the next
generation) is still open per Cursor's instruction — documented as a
business decision needed, not resolved, no option chosen by either agent.

Phase 2 remains `READY_FOR_REVIEW`: Finding 1 resolved and verified;
Finding 2 intentionally left as an open business decision, not a code
defect to fix; database verification remains `NOT_VERIFIED` pending an
authorized isolated SQL Server instance.

## Pre-outage SQLite capture (Claude, claimed 2026-10-19 21:44 IST)

**Correction accepted from the owner:** my earlier "verified current state"
entry (database_health() reachability check) is **not** a schema capture.
Confirmed by listing `docs/database-capture/` — it does not exist yet. No
SQLite reference database has been created. Starting the real capture now;
~36 minutes remain before the ~22:20 IST outage window.

**Owner redirect:** "this new UI everything based on OrderNMc db" — capture
priority is `OrderNMC` (the legacy console's live database on `.73`), not
`NEXORA_PLATFORM`/`procurement.*`. Capturing `OrderNMC` first.

**Claim:** `docs/database-capture/**` — CLAUDE, new directory. Will not
touch any Cursor-owned file in this pass. Read-only against `.73` (no
writes, no migrations, one connection, `INFORMATION_SCHEMA` + small row
samples only).

**Plan:**
1. One connection to `OrderNMC` via the existing `database.central_connection_string()`.
2. `INFORMATION_SCHEMA.TABLES`/`COLUMNS`/`KEY_COLUMN_USAGE`/`TABLE_CONSTRAINTS`
   for every user table — not just procurement-adjacent ones.
3. `sys.indexes`/`sys.index_columns` for index definitions.
4. `dbo.Stores` row set (store identity, not credentials) to find real
   store names for sampling.
5. Small deterministic samples (row-count-capped) from `OrderManagement`,
   `ProductSaleInformation`, `ProductTrans`, `PurchaseTrans`,
   `SupplierProductMatch`, `SupplierStock`, `Stores`, products — scoped to
   2-3 real store names found in step 4, with credentials/passwords masked.
6. Write everything into `docs/database-capture/nexora_schema_reference.sqlite`
   with tables: `capture_manifest`, `captured_tables`, `captured_columns`,
   `captured_indexes`, `captured_constraints`, `store_inventory`,
   `sampled_rows` (JSON blob per row + source table + store), `capture_errors`.
7. Write `docs/database-capture/CAPTURE_MANIFEST.md` summarizing exactly
   what was captured, what was skipped, and why.

Will not capture: credentials/passwords (masked in `store_inventory`), any
column that looks like a secret, full table contents (sampled only, capped
row count per table, documented in the manifest).

## Claude — Phase 2 master-task re-review (2026-10-19 23:15 IST)

**Unblocking Cursor's 23:00 IST request** ("BLOCKED — no independent
reviewer ran"). Read `PROJECT.md`, this control file, `PHASE_2_VPL_HISTORY.md`,
`PHASE_2_CLAUDE_REVIEW.md`, both VPL test files, `vpl_history.py`,
`vpl_history_router.py`, and current git status before touching anything.
Confirmed on disk (not assumed from prior reports): both review files,
both VPL test files, both VPL implementation files, `tests/test_procurement_phase2_alignment.py`,
`tests/test_procurement_rules_auth.py` all exist. **No VPL frontend UI
files exist anywhere under `frontend/src`** — confirms "VPL UI was not
started" and the master prompt's own "no new screen in this phase."

**Item 1 (Finding 1) — re-verified a second time, independently:**
`pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q`
→ **16 passed** (grew from 15 — Cursor added
`test_repeated_refreshes_never_reuse_an_earlier_row_version`, confirmed
to cover both the touched and untouched paths across 4 refreshes, not a
duplicate of my own repeated-refresh test which only covers untouched).
Cursor also strengthened the main regression test to assert the rejected
stale write leaves `supplier_code`/`rare_confirmed`/`reviewed_at`
unchanged, not just `final_qty` — satisfies the fix spec's exact wording.
Broader suite: `pytest tests/test_procurement_rules_auth.py
tests/test_procurement_rules_registry.py tests/test_quantity_profile_t.py
tests/test_procurement_formula_compare.py tests/test_procurement_phase2_alignment.py
tests/test_procurement_decision_engine.py -q` → **62 passed, 2 failed**,
same two pre-existing failures (`test_excluded_missing_grn_watermark`,
`test_spike_floor_included_binding`) byte-for-byte matching what was
recorded at session start — confirmed not a new regression, not just
assumed. `git diff --stat` on the three live-engine files: zero diff,
confirmed again.

**Item 2 (Finding 2) — reading confirmed, options now documented.**
Cursor's "no owner approval, `refresh()` correctly left unchanged" reading
is correct — I independently searched the same four files and found no
explicit choice either. Wrote the full options analysis the master task
required (A: keep live with a new unavailable status; B: drop from live,
add a dedicated removed/review query surface; C: reason-code-aware
re-inclusion, needs generation-layer changes, out of scope) into
`PHASE_2_CLAUDE_REVIEW.md`'s new "Claude re-review" section, with
affected code (`vpl_history.py` `refresh()` lines 105-147), risk
(rare-mover confirmations can vanish from the PM's view without an
audit-visible event, even though the master prompt requires visible PM
confirmation for rare movers), and acceptance tests sketched per option.
**Recommendation: Option B** (least new surface, fits the existing
drawer/history UI pattern) — explicitly labeled a recommendation, not an
approved rule. No code changed for this item; still blocked on an owner
decision.

**Noted, not investigated (out of scope for this task):**
`docs/database-capture/nexora_schema_reference.sqlite` and
`SCHEMA_DIFF_REPORT.md` now exist on disk but capture `NEXORA_PLATFORM`
schema+counts only (23 tables, 440 columns, no row samples, captured
2026-10-19T16:19:52Z against `CLIENT-3\SQLEXPRESS`) — this does not match
the `OrderNMC`-priority, row-sample-inclusive plan I recorded earlier in
this file. Did not reconcile or re-verify this capture in this pass;
flagging for whoever owns the pre-offline-capture task next.

**Files touched this task:** `docs/procurement-workspace-unification/PHASE_2_CLAUDE_REVIEW.md`
(appended, did not rewrite prior content). No Cursor-owned implementation
file edited. `tests/test_vpl_history_claude_edge.py` not modified this
pass (no new edge case was needed; existing 7 tests plus Cursor's 9 cover
the request).

Phase 2 status: `READY_FOR_REVIEW`. Finding 1 resolved and now
independently verified twice. Finding 2 fully documented with options and
a non-binding recommendation, still awaiting an explicit owner decision
before any code changes. Database verification remains `NOT_VERIFIED`.

## Ownership inventory (Cursor, 2026-10-19 23:30 IST)

Owner decision: the new procurement workflow is owned by `NEXORA_PLATFORM` schema `procurement`. OrderNMC stays the legacy operational source. Do not rewrite it, delete its tables, or replace its cycle path until a replacement is accepted and explicitly enabled. No second `order_*` set was created.

### Repository evidence (code and SQL files, not a live server)

| Concern | Canonical object in the repo | Consumers |
|---|---|---|
| New cycle | `procurement.procurement_cycles` (`sql/0001_procurement_tables.sql`) | `router.py`, `service.py`, `orchestration_router.py` |
| New refresh | `procurement.procurement_refreshes` (`sql/0002_virtual_product_list.sql`) | orchestration, VPL, Purchase Manager |
| Virtual products | `procurement.procurement_virtual_products` | `vpl_router.py`. `clear_products` still deletes one refresh's rows. |
| Working lines | `procurement.procurement_order_items` (`sql/0004`) | `pm_router.py` workspace |
| Assignments | `procurement.procurement_order_item_assignments` (`sql/0005`) | Purchase Manager assignment routes |
| Snapshot | `sql/0003_procurement_snapshot.sql` | `snapshot_router.py` |
| Rules registry | `sql/0026_*` | `rules_router.py`. **NOT APPLIED.** Process memory only. |
| VPL history | `sql/0027_*` plus in-memory `vpl_history.py` | `vpl_history_router.py`. **NOT APPLIED.** Not called by generation. |
| Legacy names | OrderNMC `dbo.order_cycles`, `order_cycle_refreshes`, `order_virtual_items` in `docs/sql/OrderNMC_PROD_migration.sql` | Legacy only. Platform equivalents are the `procurement_*` tables above. |

Frontend entry: `/procurement/workspace` (`PurchaseWorkspacePage.tsx`) and `/procurement/rules`. Electron `desktop/supplier-stock-client` is the legacy stock client. It is not the owner of new cycles.

OrderNMC reach from code, not from a new connection: `legacy_order/database.py` central connection; `order_process.py` inserts `OrderHeaderDetails`; `supplier_stock_import.py` and `distribution_service.py` read legacy stock and stores. Those paths were not changed.

### Live database evidence (separate from the repository)

- `docs/database-capture/nexora_schema_reference.sqlite` is **not on disk** in this pass. `SCHEMA_DIFF_REPORT.md` describes an earlier `NEXORA_PLATFORM` schema-and-counts capture (23 procurement tables, 440 columns, no row samples). That file is not a backup, not OrderNMC, and not proof that 0026 or 0027 are applied.
- **This pass, one read, succeeded.** `DB_NAME()` = `OrderNMC` on `CLIENT-3\SQLEXPRESS`. Table `dbo.OrderHeaderDetails`. **5914 rows.** Nine columns, matching the insert list in `order_process.py`. No extra column was present.
  - `StoreName` varchar(50) NULL
  - `OrderId` bigint NOT NULL
  - `OrderNo` int NULL
  - `OrderDateTime` datetime NULL
  - `LastSaleBillNo` varchar(50) NULL
  - `LastBillDateTime` datetime NULL
  - `LastGRN` bigint NULL
  - `MinDays` int NULL
  - `MaxDays` int NULL
- Three newest rows were sampled. Store names, sale-bill numbers, and GRN numbers were redacted. `LastBillDateTime` on those three rows was midnight (`00:00:00`). That does not describe every row. This is not a backup and does not verify procurement migrations.

### Separate statuses

- Implementation: Option A in `vpl_history.py`, in memory. Phase 2 **READY_FOR_REVIEW**.
- Independent review: **PENDING**. No Claude signature for this pass.
- UI: history screen **not built**. Existing Purchase Manager page was not edited.
- Capture: platform sqlite **absent**. OrderHeaderDetails read **done**, one table only.
- Database verification of 0026/0027: **NOT_VERIFIED**.

## Handoff log (append-only)

- **2026-10-19T21:30 IST (Claude):** Read master prompt + phase-prompts contract. Found Cursor had already completed Phase 0 (`PHASE_0_STATUS.md` = READY_FOR_REVIEW) and had substantial uncommitted Phase-1-adjacent work in `legacy_order`/desktop client already in the working tree. Independently re-ran Phase 0 fixture tests (14/14 pass, matches). Created this control file. Claiming Phase 1 source-data-contract documentation (read-only) as a non-overlapping task; leaving all live `legacy_order`/desktop files to Cursor. Next: write `14_PHASE1_SOURCE_CONTRACTS.md`.
- **2026-10-19T21:32 IST (Cursor):** Claimed P1-A. Will add `quantity_profile_t.py` and `tests/test_quantity_profile_t.py` only. Will not edit `decision_rules.py`, SQL, UI, migrations, or Claude's source-map files.
- **2026-10-19T21:36 IST (Cursor):** P1-A READY_FOR_REVIEW. `quantity_profile_t.evaluate_profile_t` matches the Phase 0 target on 14 cases. Focused pytest: 16 passed. Phase 1 not marked complete. Claude still owns the source-field map.
- **2026-10-19T21:42 IST (Claude):** Claimed and completed P1-B. Wrote `PHASE_1_SOURCE_FIELD_MAP.md` (Qty Check / Auto Purchase Update / Supplier Stock mapped to `repository.py` line references; stock source, SaleUnit/pack, pending-qty, DontConsiderInOrder findings; Role 1/2 left unmapped; 4 explicit UNKNOWNs carried forward). Independently re-ran P1-A's own test command (16 passed, matches) and confirmed zero working-tree diff on `decision_rules.py`/`decision_service.py` — P1-A's "live engine unchanged" claim checks out. No Python/SQL/UI/migration file edited; no production DB queried. P1-B now READY_FOR_REVIEW. Not starting Phase 2/3 without a review checkpoint — both P1-A and P1-B need sign-off before Phase 1 is called COMPLETE, per the master prompt's "mark complete only when evidence supports it."
- **2026-10-19T21:55 IST (Cursor):** Registered the Procurement Rules Registry workstream. Added catalog, resolution, HTTP routes, admin page `/procurement/rules`, and unapplied migration 0026 with verify and rollback SQL. `decision_rules.py` has no diff. Command: `backend\.venv\Scripts\python.exe -m pytest tests/test_procurement_rules_registry.py tests/test_quantity_profile_t.py -q --tb=short` → 8 passed (cache warning only). `npx tsc -b` in frontend exited 0. No isolated SQL Server test database, so 0026 was not executed. Overrides are process memory until that migration is approved. Claude owns `RULES_REGISTRY_CLAUDE_REVIEW.md` and has not started it in this turn.
- **2026-10-19T22:05 IST (Cursor):** Phase 1 acceptance review. Re-read the three loaders, router, generation SQL, `COLUMN_MAP`, qty commit, and stock export. 16 passed. Phase 1 marked COMPLETE. Pending column, transactionvalidity, Transactiondate time, and Role 1/2 stay blocked. No engine, schema, UI, or production-data edit. Phase 2 not started.
- **2026-10-19T22:15 IST (Cursor):** Phase 2 READY_FOR_REVIEW, not COMPLETE. Added `vpl_history.py`, `vpl_history_router.py`, `PHASE_2_VPL_HISTORY.md`, and unapplied `0027_vpl_history.sql` plus rollback and verify. `pytest tests/test_vpl_history.py -q` → 7 passed. No database connection. `decision_rules.py` and `decision_repository.clear_products` were not edited. Claude owns `PHASE_2_CLAUDE_REVIEW.md` and `tests/test_vpl_history_claude_edge.py`.
- **2026-10-19T22:45 IST (Claude):** Claimed the Phase-2 UI task. Scope found and locked in before writing code: `PurchaseWorkspacePage.tsx` (3243 lines) is already a live, production-wired VPL workspace calling real `/api/procurement/vpl*` — not a stub, and not something a second "VPL Workspace" screen should duplicate. Also found a complete app-wide day/night theme system already shipped (`ThemeContext`/`useTheme`/`ThemeToggle`/`applyTheme`/`tokens/theme.ts` with `--nx-glass-*` tokens, Bootstrap bridge, localStorage persistence, OS-preference fallback, no-flash startup) — `theme.ts`'s own comment says glass is "currently piloted by the Purchase Workspace," but `purchase-manager.css` has zero actual glass rule usage today (the match was the comment alone). Owner-approved scope for this task, confirmed via AskUserQuestion: (1) do not build a new theme system — reuse the existing one as-is; (2) do not build a second workspace screen — add a new read-only "VPL History" panel into the existing `PurchaseWorkspacePage`, backed by typed fixtures standing in for Cursor's unmounted `vpl_history_router.py`, clearly labeled; (3) apply the existing `--nx-glass-*` tokens to `purchase-manager.css` in a scoped way (header/toolbar/grid chrome/detail panel/new history panel), not a full redesign of the 3311-line stylesheet or any other screen. **Claiming:** `frontend/src/types/procurement.ts` (additive VPL-history types only, appended at EOF — done), `frontend/src/components/procurement/VplHistoryPanel.tsx` (new), `frontend/src/services/vplHistoryFixtures.ts` (new, explicit DEVELOPMENT/SAMPLE DATA), a bounded set of new CSS rules appended to `purchase-manager.css` under a clearly-delimited `/* ---- Glass surface pilot ---- */` section, and a small addition to `PurchaseWorkspacePage.tsx`'s header to open the new panel. Not editing any Cursor-owned file (`vpl_history.py`, `vpl_history_router.py`, `router.py`, 0027 SQL, `PHASE_2_VPL_HISTORY.md`'s existing content — appending a status note only). Not applying migration 0027. Not touching `decision_rules.py`/`decision_service.py`/`clear_products`.
- **2026-10-19T22:20 IST (Cursor):** Acceptance-gate check. `PHASE_2_CLAUDE_REVIEW.md` and `tests/test_vpl_history_claude_edge.py` are absent, so no Claude finding was available to fix. No implementation file was edited. Phase 2 stays READY_FOR_REVIEW. Database verification stays NOT_VERIFIED. Transaction limitation: `tests/test_procurement_phase2_alignment.py` states it opens no connection and only checks DDL text; `tests/test_vpl_history.py` exercises an in-memory lock and a `before_commit` exception. No pytest fixture starts a SQL Server transaction. Next safe task is Claude's review in the two assigned files. Do not apply 0027 and do not call `VplWorkspace` from `clear_products`.
- **2026-10-19T22:55 IST (Cursor):** Finding 1 was already fixed in `vpl_history.py` (`row_version = previous + 1` for both touched and untouched surviving lines, committed with the history append). Kept that fix. Strengthened `tests/test_vpl_history.py` so a stale pre-refresh write raises `VplConflict` and leaves final_qty, suggested_qty, supplier, review, and rare_confirmed unchanged, and so repeated refreshes do not reuse an earlier version. Claude's edge file already expected VERSION conflict; this pass did not rewrite its other cases. Finding 2 is documented, not changed: a touched line omitted from the next generated list leaves the live set and stays in history. Options (a) keep live as unavailable, (b) drop from the active set and show it for review in history, (c) no existing workflow found. Phase 2 stays READY_FOR_REVIEW. Migration 0027 not applied. Database verification NOT_VERIFIED. The NEXORA_PLATFORM sqlite capture is not evidence for this fix. VPL UI was not started. Claude should re-review the version tests.
- **2026-10-19T23:00 IST (Cursor):** Phase 2 acceptance. Finding 1 status set to FIXED and independently verified. Regression tests kept. Searched the control file, `PHASE_2_VPL_HISTORY.md`, `PHASE_2_CLAUDE_REVIEW.md`, and `PROJECT.md`: no explicit owner choice on Finding 2, so `refresh` was not changed. Finding 2 is a BUSINESS DECISION BLOCKER. Claude re-review of this pass is BLOCKED: no independent reviewer in this session. A request was appended to `PHASE_2_CLAUDE_REVIEW.md`. `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=short` → 16 passed. Broader suite `test_procurement_rules_auth.py`, `test_procurement_rules_registry.py`, `test_quantity_profile_t.py`, `test_procurement_formula_compare.py`, `test_procurement_phase2_alignment.py` → 39 passed. No frontend VPL files, so no `tsc`. `decision_rules.py`, `decision_repository.py`, and `decision_service.py` have no diff. Migration 0027 not applied. Database verification NOT_VERIFIED. Phase 2 stays READY_FOR_REVIEW.
- **2026-10-19T23:20 IST (Cursor) CLAIM — Finding 2 Option A.** Owner: CURSOR. **CONVERSATION APPROVAL** (this user message, not an artifact already in the repo when Claude last checked): "Retain manually touched lines missing from the next generation in a separate manual-review section, preserve edits and audit history, and prohibit automatic assignment, export, and ordering." Claude's earlier "not found in files" note remains true for that earlier check; it is not a statement that the user never approved. Files this claim will edit: `backend/modules/procurement/vpl_history.py`, `backend/modules/procurement/vpl_history_router.py`, `tests/test_vpl_history.py`, the one Option A expectation in `tests/test_vpl_history_claude_edge.py`, `PHASE_2_VPL_HISTORY.md`, `PROJECT.md`, and an append-only review request in `PHASE_2_CLAUDE_REVIEW.md`. Will not edit `decision_rules.py`, `decision_repository.py`, `decision_service.py`, or `clear_products`. Will not apply 0027. Will not connect `VplWorkspace` to live generation. Acceptance: touched omitted lines stay in "Removed from Current Suggestions — Manual Review", not in the active orderable list; values and history preserved; assign/export/order/portal rejected in the VPL service; failed refresh atomic; no duplicates on repeat; reappearance restores under the existing touched-line contract and drops the live removed copy; stale `row_version` still conflicts. Phase 2 stays READY_FOR_REVIEW.
- **2026-10-19T23:30 IST (Cursor):** Option A is in `vpl_history.py` and `vpl_history_router.py`. Combined pytest of the VPL pair plus rules auth, rules registry, quantity profile, formula compare, and phase2 alignment → **60 passed, 0 failed** (VPL pair alone was 21 passed in the prior command this session; the extra 5 are Option A tests; the broader 39 match the last acceptance baseline). Frontend not changed, so `tsc` was not run. One read-only OrderNMC connection succeeded: `dbo.OrderHeaderDetails`, 9 columns, 5914 rows. No write. 0027 not applied. NEXORA_PLATFORM was not opened. Ownership inventory appended above. Claude review of this pass is PENDING.

- **2026-10-19T23:45 IST (Claude):** Completed the UI task claimed above (`VplHistoryPanel` + wiring + glass CSS + types/service/tests). **Did not pick up the "Claude re-review of Option A" request above** — that is a different, backend-scoped task this turn's owner-approved scope was explicitly narrowed away from (confirmed via AskUserQuestion: "wire Phase-2 VPL history into the existing live page" for the UI, not a code review of `vpl_history.py`'s Option A change). Flagging this explicitly rather than silently absorbing it: **Option A review is still PENDING a reviewer**, separate from this entry. One consequence I did verify while building the UI that's relevant to that review: `vpl_history_router.py`'s `GET /history` and `GET /history/{history_id}` routes are mounted live (confirmed via `router.py` diff) and gated by `require_procurement_admin` (stricter than `PROCUREMENT_WORKSPACE`) — the new UI's history button is gated client-side on the matching `PROCUREMENT_ADMIN` capability and handles a 403 as an explicit "Admin access required" empty-state, not an error banner, since many legitimate Purchase Manager users will correctly get one. Also note for whoever reviews Option A: nothing in the live `PurchaseWorkspacePage` ever calls `POST /vpl-history/working` or `POST /vpl-history/refresh`, so today this history list is empty for every store in practice — documented in the new UI code and types as an explicit empty-state, not hidden.

**UI deliverable summary (Phase 2 VPL History UI, Claude):**
- Reused the existing live `PurchaseWorkspacePage.tsx` (3243 lines, already production-wired to `/api/procurement/vpl*`) rather than building a second/duplicate workspace screen — confirmed via AskUserQuestion this was the owner-intended scope.
- Reused the existing app-wide theme system (`ThemeContext`/`useTheme`/`ThemeToggle`/`applyTheme`/`tokens/theme.ts`) and the already-extensive `--nx-glass-*` glass treatment already applied throughout `purchase-manager.css` (header, toolbar, grid headers, drawers, popovers, reduced-transparency fallback, dark mode) — did NOT build a new theme system; one was already shipped and working.
- New: `frontend/src/components/procurement/VplHistoryPanel.tsx` — read-only latest-10-batches list + read-only line-level batch detail, calling the real mounted `GET /api/procurement/vpl-history/history` and `GET /api/procurement/vpl-history/history/{id}` (no fixtures needed — the route is live, just functionally dormant). Handles: loading, empty (`No archived batches...` with an honest explanation of why), 403 (`Admin access required`, not an error), and fetch-error (`ErrorState` with retry) states. Never shows an edit control — historical rows are not editable from this component.
- New types in `frontend/src/types/procurement.ts`: `VplHistoryLine`, `VplHistoryBatch`, `VplHistoryListResult`, `VplHistoryDetail` — field-for-field matched against `vpl_history.py`'s actual `_public`/`history_headers`/`history_detail` return dicts, not guessed.
- New service functions in `frontend/src/services/procurementService.ts`: `vplHistoryList`, `vplHistoryDetail`, following the existing `api.get` convention.
- `PurchaseWorkspacePage.tsx`: added a "VPL History" clock-icon button in the `pm-header__tabs` row, next to the existing context-switch button, gated on `useAccess().can('PROCUREMENT_ADMIN')` to match the server-side gate — a non-admin user never sees the button, and if they somehow reach the panel anyway (direct state manipulation, future regression), the panel itself handles the resulting 403 gracefully rather than crashing or showing a raw error.
- `purchase-manager.css`: two small, scoped additions — added `.pm-modal` to the already-existing glass selector list (alongside `.pm-settings`, `.pm-drawer`, `.pm-srpcard`) and to the matching `prefers-reduced-transparency` fallback block. This makes `VplHistoryPanel` (and the pre-existing `HistoryAllDialog`, `ManualProductModal`, etc., which all share `.pm-modal`) consistently glass without touching any other selector or redesigning the 3311-line stylesheet.
- **Not done / explicitly out of scope this pass:** no new app-wide theme system (none needed — already shipped), no second workspace route, no changes to `vpl_history.py`/`vpl_history_router.py`/`router.py`/any 0027 SQL/`decision_rules.py`/`decision_service.py`/`clear_products`, migration 0027 not applied, no live refresh wiring (the live Purchase Manager still never calls `POST /vpl-history/working` or `/refresh` — that remains a separate, unauthorized-for-this-pass phase-gate decision per the master prompt).
- **Tests:** new `frontend/src/services/vplHistoryService.test.ts` (3 tests: list call shape, detail call shape, 403→ApiError) using the existing `apiClient.test.ts` fetch-stub pattern (no new test dependency). Full suite: `npx tsc -b` → exit 0 (clean). `npx vitest run` → **44 passed, 0 failed** (41 pre-existing + 3 new), 8 test files.
- **Browser/visual verification: NOT performed.** No chromium binary and no Playwright install were available in this sandbox (network-restricted `npx playwright install` was declined automatically). Started the Vite dev server (`localhost:5173`, confirmed serving) and the already-running backend (`localhost:8000`, confirmed `/docs` responds) to attempt it, but had no browser automation tool to drive a window — stopped the dev server afterward rather than leave it running unobserved. This is a real gap: the glass CSS/theme behavior is level-reviewed against the existing (already-shipped, already-tested-elsewhere) token system, not visually confirmed in this session. Flagging per "do not claim browser verification unless actually launched and exercised."
- Capability/permission note: this UI change does not touch any backend authorization — `require_procurement_admin` was already enforcing the real boundary before this task; the new button is a convenience that matches, not replaces, that server-side check.
- **2026-10-19T23:55 IST (Cursor):** Architecture decision recorded: APPROVE WITH CONDITIONS. Existing orchestration, VPL, snapshot, and decision repositories already use NEXORA_PLATFORM. No ownership rewrite. Finding 2 Option A stays in memory. Re-ran `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=short` → **21 passed**. Broader suite (rules auth, rules registry, quantity profile, formula compare, phase2 alignment) → **39 passed**. Combined with the 21 is **60 passed, 0 failed**. Schema mapping written in `PHASE_2_VPL_HISTORY.md`. No new migration. 0027 not applied. VPL screen route `/procurement/vpl-history` behind `PROCUREMENT_ADMIN` and flag `nexora.vplHistoryScreen` / `VITE_VPL_HISTORY_SCREEN` defaulting off. Not wired to live generation. `npx vitest run src/pages/procurement/vplHistorySession.test.ts src/services/vplHistoryService.test.ts` → **12 passed**. `npx tsc -b` exited 0. Claude review of this pass is PENDING. Phase 2 stays READY_FOR_REVIEW. Database verification stays NOT_VERIFIED.
- **2026-10-19T23:59 IST (Cursor):** Schema proposal only. Recommended child-row assignment snapshots, a future `rare_confirmed` bit that was not scripted, and a separate removed-line table that is not an order item. No SQL file added. 0027 not applied. `VplWorkspace` not connected to persistence. Frontend not changed. `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=short` → **21 passed**. Broader suite not re-run. Claude review of this proposal is PENDING. Phase 2 stays READY_FOR_REVIEW. Database verification NOT_VERIFIED.
- **2026-10-20 (Claude):** Closed the "Claude review of this pass is PENDING" request above. Independent review of Cursor's latest Phase 2 schema proposal appended to `PHASE_2_CLAUDE_REVIEW.md` ("2026-10-19 (later pass)" section), covering all five requested focus areas: supplier assignment multiplicity/audit, rare-mover confirmation persistence, removed-manual-review identity/retention/reappearance, optimistic concurrency/refresh atomicity, and the manual-review UI API contract. Re-ran `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py -q --tb=short` → **33 passed**, matches. Confirmed zero `git diff` on `decision_rules.py`/`decision_repository.py`/`decision_service.py`/`order_items_repository.py`/`orchestration_service.py`/`workspace_repository.py`/`assignment_service.py`/`assignment_repository.py` — live engine and live write paths untouched, again. No Cursor-owned file edited. No migration applied. No database write attempted; `NEXORA_PLATFORM` was not opened for writes in this pass. **Verdict: no new logic defect found; in-memory behavior for all five areas is internally consistent and well-tested. NOT approved for durable persistence** — four blockers recorded (no schema for removed-manual-review state, no schema/write path for a live rare-mover confirmation, `row_version` concurrency unvalidated against real SQL Server contention, multi-process/restart durability unaddressed), plus five new acceptance tests specified that do not exist yet (transaction-atomicity, concurrent-conflict, restart-survival, rare-mover round-trip, and an explicit owner decision on tenant-vs-store scoping for this router). Phase 2 stays `READY_FOR_REVIEW`. Do not apply 0027 or wire `VplWorkspace` to persistence until those four blockers are resolved.
- **2026-10-20T16:50 IST (Cursor):** Recorded owner decisions. Assignment history and removed-line persistence are APPROVED IN PRINCIPLE, not for migration. Rare-mover confirmation is NOT APPROVED. Keys, provenance, and the refresh transaction are specified in `PHASE_2_VPL_HISTORY.md`. No migration file. Live write paths listed from code: five `workspace_repository` updates plus assignment, export, GRN, and pending writers. No optimistic check added. `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=short` → **21 passed**. Frontend not changed. Claude review of this contract is PENDING. Phase 2 stays READY_FOR_REVIEW. Database verification NOT_VERIFIED.
- **2026-10-20T17:06 IST (Cursor):** Revised data contract recorded in `PHASE_2_VPL_HISTORY.md`. The 2026-10-20 independent review verdict remains BLOCK. The owner accepted the direction in principle. Persistence stays BLOCKED. History line key is `(history_id, source_order_item_id)`. Assignment child key is `(history_id, source_assignment_id)`. Source ids are historical copies, not live foreign keys. 0027 is not the parent. Skips stay on `carry_forward_skips` and do not enter the removed collection. Rare-mover persistence is not approved. Concurrency design is documented and was not coded. No migration file. `PHASE_2_CLAUDE_REVIEW.md` was not appended. `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=short` → **21 passed**. Frontend not changed. Phase 2 stays READY_FOR_REVIEW. Database verification NOT_VERIFIED.
- **2026-10-20T17:55 IST (Cursor) CLAIM:** Owner CURSOR. Will edit `vpl_history.py`, `vpl_history_router.py`, `tests/test_vpl_history.py`, and only the identity expectation in `tests/test_vpl_history_claude_edge.py` if it still requires product_code as the sole key. Will update `PHASE_2_VPL_HISTORY.md`, `PROJECT.md`, and this file. Will not edit `PHASE_2_CLAUDE_REVIEW.md`, `decision_rules.py`, `decision_repository.py`, `decision_service.py`, `workspace_repository.py`, assignment/export/GRN/pending writers, or 0027. Will not apply a migration. Persistence stays BLOCKED.
- **2026-10-20 (Claude, TEMPORARY IMPLEMENTATION OWNER — Cursor unavailable, owner-authorized this turn):** Read `PROJECT.md`, this control file (full, both halves), `PHASE_2_VPL_HISTORY.md`, `vpl_history.py`, `vpl_history_router.py`, `workspace_repository.py`, both VPL test files, and `comparison_service.py` before editing. `git status` scoped to procurement/docs/tests paths showed no concurrent edit in flight; Cursor's prior claim at 17:55 IST had not produced a diff on `vpl_history.py` yet. Implemented the two corrections Cursor's own 17:55 claim and the owner's temporary-ownership task both asked for, in the in-memory model only:
  1. **Identity key**: `vpl_history.py` now keys lines on `product_id` when present, falling back to `product_code` only when `product_id` is absent (`_key()`/new `_index()`). Two lines sharing a `product_code` with distinct `product_id`s are never merged; a line's `product_code` can change across a refresh without losing identity; a null `product_code` with a `product_id` is accepted. Router-facing lookups by `product_code` (`edit`, the four action methods) go through a new `_resolve_by_code()` that raises a new `AMBIGUOUS` `VplError` if more than one live line shares that code — not yet wired to accept `product_id` from the router, flagged as a known residual gap, not guessed around.
  2. **Skip/removal precedence**: added `_is_skip_only()` — a line is skip-only when `item_status=="skipped"` and none of `manual_override`/`supplier_code`/`rare_confirmed` is set, matching exactly what `workspace_repository.skip_item()` produces (it sets `reviewed_at` without `manual_override`). `_touched()` no longer treats bare `reviewed_at` as sufficient and excludes skip-only lines — a plain skip that drops out of the next generation stays absent from the live set (history-only), never routes to `removed_manual_review`; a skip combined with a genuine manual override or a live supplier assignment still routes to `removed_manual_review` (manual edits and assignments are never discarded by a skip). Did not invent a rule for `defer_item`-shaped lines dropping out of generation — flagged as an open question in `PHASE_2_VPL_HISTORY.md`'s new section rather than guessed.
  3. Added 8 new regression tests to `tests/test_vpl_history_claude_edge.py` (did not edit `tests/test_vpl_history.py` — all 21 of its existing cases pass unmodified, confirming backward compatibility): null/changed/shared product_code under a stable product_id, code-based lookup still works when unambiguous, skip-with-reviewed_at-but-no-override, skip-plus-override, skip-plus-assignment, explicit stale-version restatement.
  4. Test commands: `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py -q --tb=short` → **29 passed**. Broader: `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py tests/test_procurement_rules_auth.py tests/test_procurement_rules_registry.py tests/test_quantity_profile_t.py tests/test_procurement_formula_compare.py tests/test_procurement_decision_engine.py -q --tb=line` → **91 passed, 2 failed** (`test_excluded_missing_grn_watermark`, `test_spike_floor_included_binding` — the same two pre-existing failures recorded at session start; confirmed not a new regression).
  5. `git diff --stat` on `decision_rules.py`, `decision_repository.py`, `decision_service.py`, `workspace_repository.py`, `orchestration_service.py`, `order_items_repository.py`, `assignment_repository.py`, `assignment_service.py`, `comparison_service.py`, `reconciliation_service.py` → **zero diff on all ten**. **Did not open, read, or edit any file under `backend/modules/legacy_order/` or anything touching `OrderManagement`/`OrderManagementBackup`** — explicit owner instruction received mid-task, fully respected; this pass's scope was already limited to `vpl_history.py` before that instruction arrived, so nothing had to be reverted. No migration applied. No database connection opened.
  6. **This is explicitly not an independent review.** The same agent that implemented these corrections is the one reporting on them here — no separate Claude-process signature is claimed. Full writeup, including remaining owner decisions and known limitations (the `AMBIGUOUS` residual gap on code-only router lookups, the undecided `defer_item` precedence, rare-mover persistence still NOT APPROVED, everything else in the Revised data contract unchanged), is in `PHASE_2_VPL_HISTORY.md`'s new "2026-10-20 — temporary-implementer pass" section. Phase 2 stays `READY_FOR_REVIEW`. Persistence stays **BLOCKED** pending a genuinely independent re-read of this pass's two corrections before either is accepted as the contract. No migration, no persistence code, no database write authorized by this pass.
- **2026-10-20 (Claude, independent reviewer of the temporary-implementer pass):** Read `vpl_history.py` in full, re-ran `workspace_repository.skip_item`/`defer_item` comparisons, and read every new test's assertion body (not just names) before executing anything. Independently verified by direct execution that `_key()`/`_index()`/`_resolve_by_code()` correctly make `product_id` authoritative, never merge code-colliding distinct products, preserve identity across a `product_code` change, and fail closed with `AMBIGUOUS` (422 via the router's existing `_fail()`) rather than guessing on a genuine code collision. Independently confirmed `_is_skip_only()`/`_touched()` match `skip_item()`'s exact write shape and correctly preserve a manual override or supplier assignment through a skip while excluding a bare skip from manual review — all three new skip-combination tests re-run and their assertions read in full, not just their names. Confirmed `defer_item`-drop precedence is genuinely left open (no silent mishandling), matching the implementer's own disclosure. **Found one real, previously undisclosed HIGH-severity defect by direct execution, not by reading alone:** `_public()`'s `lines.sort(key=lambda line: line["product_code"])` raises `TypeError` whenever a null-`product_code` line coexists with any second line (string-coded or also-null) in the same working set — reproduced both ways. This directly undermines the stated purpose of the identity-key fix (accepting a null-coded `product_id`-only line), and the one new test meant to cover that case (`test_line_with_product_id_and_no_product_code_is_accepted_and_findable`) opens only a single line and never calls `working()`/`refresh()` with a second line present, so the crash path is never exercised — a real gap between the test's name and its actual coverage. Re-ran `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py -v --tb=short` → **41 passed** (the crash does not surface in the existing suite for the reason above). `git diff --stat` on all ten live engine/write-path files plus `vpl_history_router.py` → zero diff on all eleven; the only diff under `legacy_order/` is Cursor's pre-existing uncommitted WIP, confirmed unrelated to and unchanged by this pass. No implementation file edited by this review. No migration applied. No database connection opened. Full findings, exact reproduction, and the explicit verified/unverified split are in `PHASE_2_CLAUDE_REVIEW.md`'s new "Independent review of the temporary-implementer pass — 2026-10-20" section. **Verdict: BLOCK.** The identity-key and skip/removal logic are themselves sound, but the undisclosed `_public()` crash is a real shipped defect, not a design-contract ambiguity, and must be fixed (narrow one-line sort-key fix, not a redesign) with a regression test that actually exercises a multi-line working set containing a null-coded line before this model advances further. Phase 2 stays `READY_FOR_REVIEW`. Persistence stays **BLOCKED**.
- **2026-10-20 (Claude, fix pass — self-implemented, NOT the independent re-verification the review requested):** Fixed the confirmed `_public()` crash: `lines.sort(key=lambda line: line["product_code"])` is replaced by a new module-level `_sorted_by_identity()`, sorting `(identity_key, line)` pairs on `(product_code is None, product_code or "", _sort_token(identity_key))` — null codes sort after string codes, and two lines sharing one code get a deterministic order from the identity-key tiebreaker instead of crashing. Applied to both `lines` and `removed_manual_review.lines` in `_public()` (the removed section had the identical bug). No API response shape changed. Manually reproduced both original crash variants (`str`/`None` and `None`/`None` comparison errors) against the pre-fix code, then confirmed both resolve cleanly post-fix, before writing any test. Added 5 regression tests to `tests/test_vpl_history_claude_edge.py` that call `open_cycle()`/`working()`/`refresh()` with **more than one line present** (the prior gap's exact failure mode — a test with only one line never exercises the sort comparator): one-null-one-string, two-nulls-distinct-ids, two-ids-sharing-one-code, five-repeated-reads-deterministic-ordering, and the same scenario inside `removed_manual_review`. Each asserts actual returned `(product_id, product_code)` identities, not just absence-of-exception. `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py -v --tb=short` → **46 passed** (41 + 5 new). Broader: same 8-file suite as before → **96 passed, 2 failed**, same two pre-existing failures, confirmed unchanged. `git diff --stat` on all ten live write-path files plus `vpl_history_router.py` → zero diff on all eleven; `legacy_order/` diff unchanged from every prior check, not touched. No migration, no DB connection, no supplier action. **This fix pass does not constitute the independent verification the fix task required — it is self-implemented and self-tested by the same process that wrote the original defect's correction.** Full writeup in `PHASE_2_VPL_HISTORY.md`'s new "2026-10-20 (fix pass)" section. Phase 2 stays `READY_FOR_REVIEW`. Persistence stays **BLOCKED** until a genuinely separate reviewer reproduces the original crash against this code and independently confirms the fix.
- **2026-10-20 (Claude, independent re-verification of the sort fix):** Confirmed `git log`/`git log --all` on `vpl_history.py` return nothing — the file was never committed, so no actual prior revision exists to check out; stated this explicitly rather than skip it. Substituted a direct re-execution of the exact pre-fix line as quoted in the prior review (`lines.sort(key=lambda line: line["product_code"])`) against two synthetic line lists — both reproduced the documented `TypeError` (`str`/`NoneType` and `NoneType`/`NoneType`), confirming the original defect's reality independent of trusting the fix report. Independently exercised all five required scenarios directly against the current `vpl_history.py` (not via the shipped tests): one-null-one-string, two-nulls-distinct-ids, two-ids-sharing-one-code, ten repeated reads with stable ordering, and two null-coded lines together in `removed_manual_review` with manual edits (`final_qty`/`supplier_code`) intact and distinguishable — all five passed by direct execution. Surfaced one precise, previously-unstated consequence: `_resolve_by_code` treats `product_code=None` as an ordinary lookup value, so once two null-coded lines coexist, editing either via `product_code=None` raises `AMBIGUOUS` — correct fail-closed behavior, not a defect, but a specific instance of the already-disclosed residual gap that wasn't spelled out for null codes before. Read all five new test bodies individually: all five genuinely exercise the multi-line `working()`/`refresh()` path (not a single-line construction, the exact gap that let the original defect ship); one of the five (`test_removed_manual_review_section_also_survives_null_coded_lines`) covers only one null-coded line in the removed section, not two — a minor test-coverage gap, not a false claim, since its own docstring only claims the singular case. `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_procurement_phase2_alignment.py -v --tb=short` → **46 passed**, independently re-run. `git diff --stat` on all ten live write-path files plus `vpl_history_router.py` → zero diff on all eleven; `legacy_order/` diff unchanged pre-existing WIP; `0026`/`0027` SQL remain untracked and unapplied. No implementation file edited by this review, no migration applied, no database connection opened, no supplier action triggered. **Verdict: APPROVE WITH CONDITIONS.** The crash fix is sound and independently confirmed across every required scenario including one (two null-coded removed lines together) the shipped suite doesn't itself cover. Conditions: add a sixth regression test for two null-coded removed lines together; document the `product_code=None`-ambiguity consequence explicitly in `PHASE_2_VPL_HISTORY.md`; the three previously-carried-forward unresolved items (broader `AMBIGUOUS` router gap, `defer_item` precedence, rare-mover NOT APPROVED) are unchanged. Full findings in `PHASE_2_CLAUDE_REVIEW.md`'s new "Independent re-verification of the null-product_code sort fix" section. Phase 2 stays `READY_FOR_REVIEW`. Persistence stays **BLOCKED** — this fix clears the crash defect but does not itself unblock persistence, which still awaits the identity-contract and concurrency-design approvals already on record.
- **2026-10-21 (Claude):** Implemented owner-approved D8 (recorded in `PHASE_2_CLAUDE_REVIEW.md`'s decision register): all 10 `distribution_*` routes in `pm_router.py` (enumerated by `grep`, matching the prior independently-verified count) now require `require_procurement_admin` instead of `require_procurement_workspace`, matching the admin-only frontend route `/procurement/distribution`. `access.py` needed no change — `require_procurement_admin` already existed from the earlier P0 task. `distribution_service.py` not touched. Added 5 new tests to `tests/test_procurement_pm_router_auth_round2.py` proving a workspace-only grant is now rejected on every one of the 10 routes (the exact case the pre-existing 13-test suite could not have caught, since every one of its own distribution checks used `PROCUREMENT_ADMIN`, which also satisfies the old `workspace` gate — confirmed by re-running the old 13 against the new code before adding anything: all 13 still passed on their own). `pytest tests/test_procurement_pm_router_auth.py tests/test_procurement_pm_router_auth_round2.py -v` → **27 passed**. Broader: `pytest tests/ -k "procurement or vpl_history" --ignore=tests/test_table_creation_engine.py` → **159 passed, 11 failed**, same 11 pre-existing failures by exact name as every prior section of this document (154 baseline + 5 new = 159, confirmed no drift). `git diff --stat` on `decision_rules.py`/`decision_repository.py`/`decision_service.py`/`vpl_history.py`/`vpl_history_router.py`/`rules_catalog.py`/`rules_resolution.py`/`rules_router.py`/every `sql/` file → zero diff on all. `legacy_order/` pre-existing Cursor WIP untouched, not opened. No migration applied, no database connection, no WhatsApp/export/GRN action. Full writeup in `PHASE_2_CLAUDE_REVIEW.md`'s new "D8 implementation — 2026-10-21" section. **D8 status: `OWNER APPROVED — IMPLEMENTED`**, pending one more independent review pass before being treated as fully closed, consistent with every prior authorization task in this thread. Phase 2 stays `READY_FOR_REVIEW`. Persistence stays `BLOCKED`. Rare-mover untouched.
- **2026-10-21 (Claude, independent re-verification of D8 — this pass):** Re-read the D8 decision record and implementation writeup in `PHASE_2_CLAUDE_REVIEW.md`, then independently confirmed by direct inspection: grep'd all 10 named route functions in `pm_router.py` and read each decorator's dependency line directly — all 10, and only those 10, inject `Depends(require_procurement_admin)`; none inject `require_procurement_workspace`. Re-ran `pytest tests/test_procurement_pm_router_auth.py tests/test_procurement_pm_router_auth_round2.py -q --tb=short` fresh in this pass → **27 passed**, matching the implementation entry exactly, no drift. `git diff --stat` confirms `pm_router.py` is the only modified tracked file among the D8-relevant set; `access.py` is untracked (new file, no prior committed baseline — consistent with "no change needed, already existed from P0"); `distribution_service.py` shows no diff attributable to D8. No real SQL Server/JWT integration test exists for this or any prior authorization pass in this document — unchanged, remains explicitly `NOT_VERIFIED`. No implementation file edited by this review. No migration applied, no database connection opened, no external action taken. **Verdict: APPROVE. D8 is closed.**
- **D8 status: `CLOSED — owner-approved, implemented, independently re-verified twice`.** Capability swap (`require_procurement_workspace` → `require_procurement_admin`) confirmed on all 10 `distribution_*` routes by direct code inspection; 27/27 focused authorization tests pass; tenant/resource ownership checks (`assert_tenant_access`, trusted `run_tenant_id`/`run_item_tenant_id` lookups) confirmed unmodified. **Outstanding limitation, carried forward, not cleared by this closure:** no live SQL Server/JWT integration test has been run for D8 or any authorization work in this document — all verification is mocked-service/in-process `TestClient` only. This does not block closing D8 (a known, explicitly-documented gap across the whole authorization workstream, not a D8-specific defect) but must stay visible in the Step 5 release gate as `NOT VERIFIED (mocked only)` for the authorization/authentication gate.
- **2026-10-21 (Claude) — D3c decision obtained and implemented.** Owner decision (via explicit question, this session): discrete `rare_confirmed` field, not queue-based. Implemented: migration `0028_rare_mover_confirmation.sql` (+verify+rollback, additive, NOT APPLIED), `rare_mover_guard.py` (new, feature-gated behind `PROCUREMENT_RARE_MOVER_ENFORCEMENT`, default off — 0028 isn't applied so the column doesn't exist live; unconditional enforcement would permanently block every rare-mover line), enforcement wired into `assignment_service.assign_single`/`assign_bulk` (per-item isolation preserved) and `export_service.export_refresh`/`export_repository.exportable_assignments` (whole-batch fail-closed), new `POST /order-items/{id}/confirm-rare-mover` route + `workspace_service.confirm_rare_mover` + `workspace_repository.confirm_rare_mover`. Full writeup in `PHASE_2_CLAUDE_REVIEW.md`'s new "D3c implementation" section (D1-D8 register updated, D8 also marked CLOSED there). Tests: `pytest tests/test_procurement_rare_mover_guard.py -v` → **15 passed**. Broader: `pytest tests/ -q -k "procurement or vpl_history" --ignore=tests/test_table_creation_engine.py` → **174 passed, 11 failed**, same 11 pre-existing failures by exact name, no drift (159 baseline + 15 new). `git diff --stat` on all live-engine files (`decision_rules.py`/`decision_repository.py`/`decision_service.py`/`vpl_history.py`/`vpl_history_router.py`/`rules_catalog.py`/`rules_resolution.py`/`rules_router.py`) → zero diff. `legacy_order/` untouched (Cursor's pre-existing WIP). No migration applied, no DB connection, no external action. **D3c status: implemented, self-reviewed only — a genuinely separate reviewer should still re-verify before this is treated as closed**, consistent with every prior authorization task in this document. Moving to Step 3 (concurrency) next, per the master prompt's sequential protocol.
- **2026-10-21 (Claude) — Step 3 concurrency (D4/D5) implemented.** D1/D2/D6/D7 re-confirmed to need no code change (already matched by current code). D4: new `assignment_repository.lock_order_item_for_assignment` (`WITH (UPDLOCK, HOLDLOCK)`), wired into `assign_single`/`assign_bulk` before the existing duplicate/active-assignment checks — fixes the TOCTOU race documented in this file's "Audit D item 2". D5: owner decision obtained (client-supplied `idempotency_key`, not a dedup window); new migration `0029_refresh_idempotency_key.sql` (+verify+rollback, NOT APPLIED), `vpl_repository.find_by_idempotency_key`, `create_vpl` conditional column write, `orchestration_service.create_refresh` idempotency check + concurrent-insert race recovery — feature-gated behind `PROCUREMENT_REFRESH_IDEMPOTENCY` (default off, same pattern as D3c's flag). New `tests/test_procurement_concurrency_d4_d5.py` — 8 passed. One additive mock line added to the shared `tests/test_procurement_pm_workflow.py` (`_patch_assign` + `test_bulk_assign_reports_mixed`) so the new D4 lock call doesn't collide with that file's existing `_FakeConn` fixture gap — confirmed the three tests that still fail there (`test_assign_single_ok`, `test_assign_exceeds_final_rejected`, `test_bulk_assign_reports_mixed`) fail on the same pre-existing `any_active_assignment` gap both before and after this change, not newly broken. Broader: `pytest tests/ -q -k "procurement or vpl_history" --ignore=tests/test_table_creation_engine.py` → **182 passed, 11 failed**, same 11 pre-existing failures, no drift. `git diff --stat` on all live-engine files → zero diff except `workspace_repository.py` (Step 2's `confirm_rare_mover` addition). No migration applied, no DB connection, no external action. Full writeup in `PHASE_2_CLAUDE_REVIEW.md`'s "Step 3" section. **Step 3 status: implemented, self-reviewed only.** Moving to Step 4 (VPL History persistence) next.
- **2026-10-21 (Claude) — Step 4 VPL History persistence (repository layer).** New migration `0030_vpl_history_persistence.sql` (+verify+rollback, NOT APPLIED) implementing the already-accepted "Revised data contract" (batch/line/assignment-child/removed-line tables, superseding 0027's batch/line design per its own "0027 is not the parent" note) plus the Concurrency design's `row_version` columns on assignments/refreshes. New `vpl_history_repository.py` (Claude-owned, new file — did not edit Cursor-owned `vpl_history.py`/`vpl_history_router.py`): `write_history_batch` (one transaction), removed-line upsert/restore (fails closed on concurrent double-restore), reads. **Not wired into live `create_refresh`** — found during this pass that `procurement_order_items` rows for a prior refresh are never actually deleted by the live pipeline (they just stop being "current"), narrowing the real urgency vs. what the in-memory prototype assumed; wiring is a flagged follow-up, not attempted this pass. New `tests/test_vpl_history_repository.py` — 9 passed. Broader: `pytest tests/ -q -k "procurement or vpl_history" --ignore=tests/test_table_creation_engine.py` → **191 passed, 11 failed**, same 11 pre-existing, no drift. `git diff --stat` on all live-engine files + `vpl_history.py`/`vpl_history_router.py`/`order_items_repository.py` → zero diff (only `orchestration_service.py` has Step 3's diff). No migration applied, no DB connection, no external action. Full writeup in `PHASE_2_VPL_HISTORY.md`'s "Step 4" section. **Step 4 status: repository layer implemented and tested, NOT wired to live generation, self-reviewed only.** Moving to Step 5 (release gate) next.
- **2026-10-21 (Claude) — Isolated SQL Server integration verification, real DB.** Phase A found an isolated candidate (localhost\SQLEXPRESS, no NEXORA_PLATFORM/OrderNMC on it) separate from the shared .73 production node; owner approved creating NEXORA_PLATFORM_TEST there. Phase B readiness report presented before any write. Phase C: applied 0001-0008+0028+0029+0030, all verified cleanly; ran 23 real-SQL-Server scenarios (D3c confirmation incl. cross-tenant/cross-cycle, D4 two-real-connection concurrent assign race, D5 two-real-connection concurrent refresh-key race, Step 4 repository incl. real forced-failure atomicity) — all 23 passed. **Found and fixed two real defects**: 0028's and 0030's rollback scripts' `RAISERROR+RETURN` guard only exited its own `GO` batch in sqlcmd, not the whole script — the refusal message printed but the DROP statements ran anyway. Reproduced directly (seeded real confirmed/history data, ran rollback, confirmed via direct schema query that data-destroying statements executed despite the refusal), fixed both scripts with a `#rollback_NNNN_guard` temp table checked at the top of every later batch, re-verified both fixes twice each (blocked case now correctly leaves everything intact; empty case now correctly succeeds). Dropped NEXORA_PLATFORM_TEST at the end — zero footprint on the local instance. Re-ran the full mocked pytest suite afterward: 191 passed, 11 failed, identical to every prior checkpoint (SQL-only fix, no Python changed). Files changed: `0028_rare_mover_confirmation_rollback.sql`, `0030_vpl_history_persistence_rollback.sql` only. Full writeup in `PHASE_2_CLAUDE_REVIEW.md`'s new "Isolated SQL Server integration verification" section. **Verdict: PASSED.** Production `.env`/`.73`/`OrderNMC` untouched throughout. Release gate 4/5/6 upgraded from mocked-only to real-SQL-Server-verified for the tested scenarios; VPL History→create_refresh wiring remains the one explicitly-stated open gap.
- **2026-10-22 (Claude) — Step 4b: VPL History wired into live `create_refresh`.** Closes the gap flagged in the Step 4 entry above. New `vpl_history_repository.list_items_for_history(conn, tenant_id, refresh_id)` reads the previous refresh's live `procurement_order_items` rows on the same connection/transaction `create_refresh` already holds; `assignment_repository.list_by_refresh` (existing, reused) supplies the assignment children; `write_history_batch` (existing, unchanged) writes both, all inside the same `try/commit/except/rollback` block that already runs `clear_working_items`→`generate_working_items`→`carry_forward_skips`→`comparison_service.carry_forward` — so a failure anywhere in that sequence, including the history write itself, leaves no partial history batch and no deleted working set. New flag **`PROCUREMENT_VPL_HISTORY`** (default off, 0030 still NOT APPLIED, same pattern as D3c/D5). Corrected one real schema mistake before it reached a test: `reason_code` does not exist on `procurement_order_items` (confirmed by reading migrations 0004/0007/0008 directly, not trusting the in-memory prototype's field list) — dropped from the read, not guessed. Confirmed by direct code reading, not assumption: `clear_working_items` deletes rows for the *new* refresh_id (always empty), never the previous one — the history write and the delete are not racing the same rows. 6 new regression tests added to `tests/test_procurement_orchestration.py` (default-off no-op, call-order + exact-payload assertion, skip-when-no-previous-items, forced-failure rollback-and-no-partial-write with a tracking fake connection, duplicate-batch unique-violation swallowed as idempotent-retry) plus 2 pre-existing tests in that file fixed (`test_create_refresh_full_pipeline` was silently hitting a real SQL Server connection — missing `StoreRepository`/`next_refresh_no`/`get_vpl`/`carry_forward_skips` mocks — a drift gap unrelated to this task, confirmed via `git stash` to predate it, fixed as a one-line-per-mock restoration of the test's own stated "DB-free" contract). `pytest tests/test_procurement_orchestration.py -v` → **12 passed**. Focused relevant-file run: `pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_vpl_history_repository.py tests/test_procurement_phase2_alignment.py tests/test_procurement_orchestration.py tests/test_procurement_concurrency_d4_d5.py tests/test_procurement_rare_mover_guard.py -q` → **91 passed**. **Real finding, not a regression:** the broader `pytest tests/ -q -k "procurement or vpl_history"` combined run now shows 10 failed/197 passed, not the previously-recorded 191/11 — verified via `git stash` that this cross-file pollution (51 failed/151 passed) already existed on the pre-this-pass working tree, so the "191 passed, 11 failed" figure in the 2026-10-21 entries above is stale relative to the current tree's uncommitted WIP in `pm_router.py`/`export_repository.py`/`vpl_repository.py`, not something this task broke; every file that fails in the combined run passes cleanly in isolation (e.g. `test_procurement_rare_mover_guard.py` 15/15 alone). `git diff --stat` on `decision_rules.py`/`decision_repository.py`/`decision_service.py`/`vpl_history.py`/`vpl_history_router.py`/`rules_catalog.py`/`rules_resolution.py`/`rules_router.py` → zero diff on all. No migration applied, no database connection opened, no production flag changed. Full writeup in `PHASE_2_VPL_HISTORY.md`'s new "Step 4b" section. **Status: implemented and tested, self-reviewed only — needs independent re-verification before closure**, consistent with every prior task in this document. GRN/reconciliation transaction-boundary investigation is next, per the master-prompt sequence.
- **2026-10-22 (Claude) — GRN/reconciliation transaction-boundary audit (investigation only, no code changed).** Traced `submit_grn`/`reconcile` (`reconciliation_service.py`) end to end. **Confirmed defect:** `submit_grn` ran as TWO separate transactions — Transaction A (`store_last_grn`, own connection, own commit) then Transaction B (`reconcile`'s own fresh `get_connection()`, own commit) — so a `reconcile` failure left `last_grn_number`/`grn_completed_at` durably committed with zero reconciliation applied, with no audit trail recording the stuck state (grepped `sql/*.sql` for "audit" near GRN columns — zero matches; no such table exists). Confirmed the internal assignment-loop/item-rollup-loop writes inside `reconcile` were already atomic (single shared connection, single commit, rollback-on-exception) — the gap was only the A/B split, not the loops themselves. Also found and flagged (not fixed, per scope): `reconciliation_repository.read_purchase_receipts` accepts a `last_grn` parameter it never uses in its SQL — reconciliation always reads ALL-time `sync.PurchaseTrans`, not receipts bounded by the Last GRN watermark its own docstring implies; and `close_cycle`'s per-refresh reconcile loop swallows every exception (`except Exception: logger.exception(...)`, no re-raise), so a reconciliation failure for one refresh during cycle close is silently absorbed. Both flagged as owner decisions needed, not touched.
- **2026-10-22 (Claude) — GRN/reconciliation transaction-boundary fix, implemented.** Gave `reconciliation_service.reconcile` an optional `conn=None` parameter: when `None` (default), behavior is byte-for-byte unchanged — opens its own connection, commits/rolls back/closes itself, exactly as before (this is `close_cycle`'s call path, confirmed by inspection it passes no `conn` argument — its per-refresh isolation, one connection per refresh, each independently committed, is preserved, not touched). When a caller passes `conn`, `reconcile` runs entirely on that connection and leaves commit/rollback/close to the caller. `submit_grn` now opens ONE connection, calls `repo.store_last_grn(conn, ...)` then `reconcile(..., conn=conn)` on it, and commits once at the end (rollback on any exception from either step) — closing the exact gap from the audit. No schema change, no migration, no new table — pure connection-passing refactor, as the audit recommended as the smallest safe correction. **Deliberately not touched, per explicit scope:** `close_cycle`'s swallow-and-continue behavior (unchanged; still an open owner decision, reported again here); `read_purchase_receipts`'s unused `last_grn` argument (unchanged; still an open owner decision); no audit table added (schema change, separate decision).

  **Files changed:** `backend/modules/procurement/reconciliation_service.py` (`submit_grn` + `reconcile`, ~37 lines net), `tests/test_procurement_sprint3.py` (6 new tests + a `StoreRepository` mock fix to one of the new tests' own `close_cycle` call, ~339 lines).

  **Tests — new, in `tests/test_procurement_sprint3.py`, all using tracking fake connections (unit-level only, mocked repository — explicitly NOT a real-SQL-Server verification):**
  - `test_submit_grn_success_commits_grn_and_reconcile_on_one_connection` — asserts `store_last_grn` and `reconcile` both ran on the *same* connection object and exactly one `commit()`/zero `rollback()`/one `close()` occurred.
  - `test_submit_grn_reconcile_failure_rolls_back_grn_update_too` — forces `read_purchase_receipts` to raise; asserts the shared connection rolled back (not committed) — directly proves the audit's confirmed defect is closed.
  - `test_submit_grn_failure_in_assignment_loop_rolls_back_grn_and_prior_assignments` — two assignments, the second's `apply_receipt` raises; asserts both were attempted (loop ran) but the whole transaction rolled back, and the rollup loop was never reached (`AssertionError` wired into `order_items_for_refresh` if it is).
  - `test_submit_grn_failure_in_item_rollup_rolls_back_grn_and_assignment_writes` — assignment loop succeeds, `item_received_total` then raises; asserts rollback covers the already-applied assignment write too, and `set_item_receipts` is never reached.
  - `test_submit_grn_retry_after_failure_succeeds_on_shared_connection` — first call's `read_purchase_receipts` raises (rolled back, fresh connection object), second call with the same inputs succeeds cleanly on a brand-new connection — proves retry-after-failure works and that `get_connection()` is called fresh per attempt (no cross-call connection reuse/poisoning).
  - `test_close_cycle_reconcile_still_opens_its_own_connection_per_refresh` — two refreshes in one cycle; asserts `close_cycle`'s existing conn-less `reconcile` call still opens two independent connections (one per refresh) and each commits independently — the regression guard proving this fix did not alter `close_cycle`'s isolation.

  **Exact test run:**
  ```
  backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_sprint3.py -v --tb=short -k "grn or reconcile or GRN"
  → 8 passed (2 pre-existing unchanged + 6 new)

  backend/.venv/Scripts/python.exe -m pytest tests/test_procurement_sprint3.py -v --tb=short
  → 18 passed, 5 failed — same 5 pre-existing failures (test_manual_add_validations: pending_repository API drift; test_close_cycle_blocked_when_generating/test_close_cycle_ok/test_close_cycle_already_closed/test_end_to_end_post_export: pre-existing close_cycle(tenant_id, cycle_id, grn, bill, by) 5-positional-arg signature drift already documented in the prior VPL History task) — confirmed via git stash to predate this change (stashed tree: identical 5 failed, 12 passed; this pass added 6 new passing tests, zero regressions).

  backend/.venv/Scripts/python.exe -m pytest tests/test_vpl_history.py tests/test_vpl_history_claude_edge.py tests/test_vpl_history_repository.py tests/test_procurement_phase2_alignment.py tests/test_procurement_orchestration.py tests/test_procurement_concurrency_d4_d5.py tests/test_procurement_rare_mover_guard.py tests/test_procurement_sprint3.py tests/test_procurement_pipeline.py -q
  → 114 passed, 5 failed (same 5 as above)
  ```

  **Verification level — stated accurately, not overclaimed:** all of the above is mocked-repository, tracking-fake-connection unit testing. It proves the Python-level transaction-boundary logic (what gets committed/rolled back and in what order) but does NOT prove real SQL Server transaction/isolation behavior. No isolated SQL Server instance was used for this pass (unlike the Step 4/D4/D5 real-DB verification in the prior task) — the concurrent-reconcile lost-update race (audit scenario 6) and real commit/rollback durability under this new connection-sharing shape remain `NOT_VERIFIED` against a real server. Flagging as the natural follow-up if/when another isolated-instance pass is authorized.

  `git diff --stat` on `decision_rules.py`/`decision_repository.py`/`decision_service.py`/`vpl_history.py`/`vpl_history_router.py`/`rules_catalog.py`/`rules_resolution.py`/`rules_router.py`/`orchestration_service.py` → zero diff on all (this pass touched only `reconciliation_service.py`, confirmed scoped — `reconciliation_repository.py` and `reconciliation_rules.py` are unchanged too). No migration applied, no database connection opened to a real server, no production flag changed, no commit/push made.

  **Unresolved owner decisions, carried forward from the audit, untouched by this fix:**
  1. Should `close_cycle`'s per-refresh reconcile failures continue to be silently swallowed, or surfaced in its response (e.g. "2 of 3 refreshes reconciled")?
  2. Should `read_purchase_receipts` actually filter by the `last_grn` watermark it already accepts, or is all-time receipts the intended behavior?
  3. Should a GRN/reconciliation audit table be added (schema change, separate from this fix)?

  **Status: implemented and tested at the unit level, self-reviewed only — needs independent re-verification, and ideally a real-SQL-Server pass, before closure.** Stopping for review per the task's explicit instruction.
