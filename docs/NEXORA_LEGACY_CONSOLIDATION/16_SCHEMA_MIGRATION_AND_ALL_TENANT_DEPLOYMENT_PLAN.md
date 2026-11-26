# 16 — Schema Migration & All-Tenant Deployment: Current State + Proposed Future Design

Status: READ-ON LY investigation for items 3, 6, 7 of the Phase 7C brief, PLUS a proposed (NOT implemented, NOT built) future migration strategy. No files, databases, or git state were modified. Every section below is explicitly marked **EXISTING (Verified)** or **PROPOSED (Not Implemented)** — nothing proposed here has been coded.

Tag legend: **VERIFIED** (read directly, file:line cited) · **PARTIAL** · **INFERRED** · **UNKNOWN**.

---

## EXISTING (Verified)

### 3. Migration framework

**VERIFIED — there is no Alembic, no Django-style migrations, no custom migration-runner with a tracked version table anywhere in this codebase.**

- No `alembic` directory, no `alembic.ini`, no `env.py` migration script was found anywhere under `backend/` (searched the whole tree; the only alembic-shaped hits were inside unrelated third-party vendored packages under `backend/.venv` and are irrelevant).
- No table or model matching `schema_version`, `db_version`, `SchemaVersion`, `applied_migrations`, or `migration_log` exists in application code. The only textual hits for those terms are inside vendored third-party library test fixtures (pandas/Cython/sqlalchemy test files) and raw data dumps (`nexora_platform_dump (1).sql`, `nexora_platform_export.sql`) — not application schema.

**What exists instead is a convention, not a framework**, consistently used across ~40+ modules:

**(a) Per-module numbered SQL files**, pattern `backend/modules/<module>/sql/NNNN_description.sql` (4-digit, monotonically increasing per module — e.g. `backend/modules/procurement/sql/0001_procurement_tables.sql` through `0032_tenant_export_defaults.sql`; `backend/modules/legacy_order/sql/0001_supplier_stock_rack.sql` through `0011_supplier_whatsapp.sql`). Several of the most recent `procurement` ones additionally ship paired `_rollback.sql` and `_verify.sql` files (`0026_procurement_rules_registry{,_rollback,_verify}.sql`, and likewise for `0027`–`0030`) — the closest thing in this codebase to a "real" migration (forward + rollback + verification script), but this pattern is **not used consistently** across modules; most numbered files have no rollback/verify companion.

Critically, these numbered files are **not run by any central runner that tracks "which ones have been applied to this database."** Each `.sql` file is internally idempotent on its own (`IF OBJECT_ID(...) IS NULL`, `IF COL_LENGTH(...) IS NULL`, etc. — see `backend/modules/legacy_order/sql/0010_order_skip_rules.sql:22-28` for a representative example), so re-running the same file twice is safe, but there is no table recording "migration 0010 has been applied to database X." Applying them falls into two observed patterns:

  - **Auto-applied once per backend process (not persisted).** Example: `backend/modules/legacy_order/repository.py:2048-2067` (`_ensure_skip_schema`) opens the file `sql/0010_order_skip_rules.sql`, splits it on `GO` batches, executes each batch on its own connection, commits, and sets an **in-memory module-level flag** `_SKIP_SCHEMA_READY = True` (line 2048) so it only runs once *per process lifetime* — not once ever, and not tracked in any table. Every fresh backend restart re-runs the idempotent check (cheap, since the SQL itself no-ops if already applied) but there is no durable record anywhere of "this DB is at schema level 0010." The `.sql` file's own header comment confirms this is deliberate: *"Idempotent -- also applied at runtime by repository._ensure_skip_schema, so a fresh install needs no manual step."* (`0010_order_skip_rules.sql:4-5`)
  - **Reference-only, applied by a human by hand.** Most numbered files (e.g. `backend/modules/procurement/sql/0018_supplier_export_settings.sql`, referenced only in a code comment at `procurement/supplier_export_settings_repository.py:2` — *"see sql/0018_supplier_export_settings.sql for why this is its own table"*) are **never opened or executed by any Python code at all** — they exist purely as the historical DDL record for a human (the owner/developer) to run once by hand against each target database when deploying that feature. This is the majority pattern.

**(b) Per-module `ensure_schema()` functions**, called either lazily on first use (e.g. `backend/modules/procurement/optimization_repository.py:41`, `network_movement_repository.py:25`, `product_category_repository.py:31` — all called from inside their own service functions right before doing real work) or eagerly at backend import time from `backend/api/app.py`. Confirmed at `app.py:165-197`:
```python
from modules.audit.repository import ensure_schema as ensure_audit_schema
from modules.mobile_bff.repository import ensure_schema as ensure_mobile_bff_schema
...
try:
    ensure_audit_schema()
except Exception:
    pass
try:
    ensure_mobile_bff_schema()
except Exception:
    pass
try:
    TenantRepository().ensure_schema()
except Exception:
    pass
app = FastAPI(title='NEXORA API')
```
These run **before the FastAPI app object is even constructed**, wrapped in bare `try/except: pass` — meaning a genuine DB-unreachable condition, a permissions problem, or a real DDL bug is **silently swallowed** at the exact moment schema is supposed to be guaranteed, and the app boots anyway. This is "self-healing on every boot," not "versioned migration" — there is no record of success/failure, no audit trail, and no mechanism to know, after the fact, whether `ensure_audit_schema()` actually succeeded on a given node.

`backend/modules/bootstrap/repository.py:23-61` (`ensure_schema()` for `dbo.ho_routes`) is a clean example of the pattern's shape: `IF OBJECT_ID(...) IS NULL CREATE TABLE`, then a conditional unique-index create, then a conditional one-time seed (`SELECT COUNT(*) ... IF 0 THEN INSERT seed rows`) that explicitly avoids re-seeding if an operator has already customized the table (`bootstrap/repository.py:53-55`).

**(c) The `schema_sync` module** (full detail below) — a manual Dev→Production diff/apply tool, explicitly NOT automatic and NOT tenant-aware (it diffs exactly two connections supplied by the caller at request time).

**(d) `backend/modules/sync/schema_evolution.py`** (`ensure_table(cursor, table_name)`, lines 89-147) — the one genuinely automated, idempotent, *per-table* schema-evolution routine in the codebase, but it is scoped narrowly: it only manages tables inside the `sync.*` schema that the store-data-sync merge pipeline writes into, driven by metadata rows in `sync.sync_table_master` / `sync.sync_column_mapping` / `sync.sync_schema_catalog` (queried at `schema_evolution.py:21-40`). It is called from inside the merge transaction (docstring: *"Runs on the caller's cursor so it shares the merge transaction,"* line 91) immediately before a merge, and:
  - Creates the table in a store-scoped shape (`store_id` + `tenant_id` + mapped business columns + `row_hash`, composite PK `(store_id, <business pk cols>)`) if missing, or **rebuilds it** (DROP + CREATE) if it exists but predates the `store_id`-scoped shape (lines 101-117) — the ONLY place in the codebase a "migration" can be destructive-by-design, and it only triggers on a very specific legacy-shape detection.
  - Otherwise adds only genuinely-missing columns, **always as `NULL`** (`force_nullable=True`, line 54) specifically because SQL Server error 4901 forbids adding a `NOT NULL` column to a populated table (comment, lines 46-48) — i.e., it already encodes exactly the "backward-compatible additive change" discipline this Phase 7C effort needs, just for one schema (`sync.*`), not the whole platform.

### 6. Honest current-state assessment — does ANY automated, versioned, tenant-aware schema migration system exist?

**No.** Stated plainly, as the brief requires:

There is no system in this codebase that (a) assigns a version/ID to a schema change, (b) records in a database which version each tenant/store database is currently at, (c) can push a new schema change out to `.73`, `.32`, and `.80` (and whatever remote per-store OrderNMC/OrderSMS/OrderSuccess/OrderSuppliers databases exist) in a coordinated, trackable, retryable way, or (d) can tell an operator, without manually connecting to each database, which ones have or have not received a given change.

What exists is three independent, narrower things that together cover *some* of that ground by convention and discipline rather than by a built mechanism:
1. Idempotent, self-re-checking DDL embedded in `ensure_schema()` functions and numbered `.sql` files, re-run (cheaply, safely) on every backend boot for the subset of modules wired into `app.py`'s startup block, or on first use for the rest — but with **no cross-database visibility and no failure tracking**.
2. A human-operated Dev→Production diff tool (`schema_sync`) for doing a full schema reconciliation between exactly two databases at a time, on demand — this is precisely what the "2026-11-03 Schema sync .73→.32" memory note describes, and the code confirms it is a **manual, single-pair, point-in-time** operation, not a push/broadcast mechanism.
3. A genuinely automated per-table schema-evolution helper (`schema_evolution.py`), but scoped only to the `sync.*` tables managed by the store-sync pipeline's own metadata tables — it was built to solve a narrower problem (keep merge-target tables in sync with the sync-config catalog) and was not designed, and is not positioned, to be a general-purpose platform migration engine.

**This is the single biggest gap for the Phase 7C consolidation requirement.** If Legacy Order and Procurement Workspace are merged into one engine and that merge requires a new table/column on OrderNMC-equivalent databases across `.73`, `.32` (OrderSuccess + OrderSMS), `.80`, and any remote per-store databases, the ONLY existing path today is: a developer writes a new numbered `.sql` file (and, optionally, an `ensure_schema()`/`_ensure_*_schema()` guard function so it self-applies on next boot of each node), and/or a human manually opens the `schema_sync` tool and runs compare+apply against each target database one at a time by hand. There is no automated fan-out, no central "has database X received migration Y" ledger, and no built-in retry/rollback orchestration spanning multiple databases.

### 7. Backward-compatibility handling

**VERIFIED — extensive, consistent, battle-tested column/object-existence checking throughout the codebase. This is the strongest existing asset for the Phase 7C "must survive a missing optional column/table" requirement.**

The grep for `COL_LENGTH|Invalid column name|OBJECT_ID(|except pyodbc.Error|invalid object name` returned **52 distinct application files** (excluding vendored third-party packages), spanning `legacy_order`, `procurement`, `sync`, `device_identity`, `audit`, `nmv_integration`, `ordernmc_mirror`, `schema_sync`, `sale_analysis`, `label_exporter`, `mobile_bff`, `grid_settings`, `desktop_client`, and more. Representative verified examples:

- `backend/modules/legacy_order/database.py:222-229` (`central_store_tenant`) — before trusting a `tenant_id` column exists on a remote/older `OrderNMC` schema, it explicitly checks `SELECT COL_LENGTH('dbo.Stores', 'tenant_id')` and returns `None` gracefully (*"no row, or an OrderNMC without the tenant_id column"*) rather than letting the subsequent `SELECT tenant_id FROM dbo.Stores` throw on a database that predates that column. This is a direct, working example of exactly the "optional column may not exist yet on an older tenant DB" pattern the Phase 7C requirement needs for Legacy Order's survival.
- `backend/modules/sync/schema_evolution.py:66-86` (`_col_exists`) — queries `sys.columns`/`sys.tables`/`sys.schemas` directly (not `COL_LENGTH`, for case/whitespace-insensitive comparison) before deciding whether to `ALTER TABLE ... ADD` a column, explicitly to avoid ever reporting an existing column as missing due to a casing/trailing-space mismatch (comment, lines 71-73).
- `backend/modules/schema_sync/service.py` — the whole compare/apply tool is fundamentally built around "does the target already have this object" checks (`IF OBJECT_ID(...) IS NOT NULL`, `IF NOT EXISTS (SELECT 1 FROM sys.schemas ...)`, etc. — e.g. lines 225-228 for schema existence, 173 for programmable-object existence) before ever emitting a DDL statement, and its `apply()` (lines 525-538) is explicitly "best-effort: runs every statement even if an earlier one fails... so one bad statement never blocks unrelated tables/indexes/procs" — an explicit per-statement failure-isolation discipline, though still with no durable tracking of which statements previously succeeded on a given target across separate `compare`/`apply` calls.
- `backend/modules/legacy_order/database.py:284-293` (`_tenant_legacy_db_name`) — wraps its platform-DB lookup of `dbo.tenants.legacy_db_name` in `try/except Exception`, explicitly falling back to the cached value or `None` rather than raising, with the comment *"Platform DB hiccup must not break the legacy console."*
- Module-level `try/except: pass` around every `ensure_schema()` call at backend startup (`backend/api/app.py:184-197`) — already discussed above as a migration-tracking weakness, but it is simultaneously a *backward-compatibility* strength: a node whose DB is missing a brand-new table/column for a feature it doesn't yet have provisioned will not crash the whole backend on boot.

**Net assessment for item 7**: the codebase does not have a single named "feature flag gated on schema presence" abstraction, but it has the *functional equivalent*, repeated consistently as an idiom: check `COL_LENGTH`/`OBJECT_ID`/`sys.columns` before touching a column/table that might not exist yet, and degrade to `None`/skip/fallback rather than propagating the SQL error. This idiom is exactly what any new Legacy Order + Procurement Workspace consolidation code should keep using for new, not-yet-everywhere-deployed schema.

---

## PROPOSED (Not Implemented)

Everything below is a **design proposal only**. Nothing in this section has been built, and nothing here should be read as describing current behavior. It is offered because the owner's Phase 7C requirement explicitly asks for a forward-looking plan; it extends the *existing* idioms above rather than inventing an unrelated framework, specifically so it can be adopted incrementally without a disruptive rewrite.

### Design goals
- Reuse the existing idempotent-DDL idiom (`IF OBJECT_ID/COL_LENGTH IS NULL`) — do not replace it, wrap it.
- Work across an unknown, possibly-growing set of physical databases (`.73`, `.32`'s OrderSuccess/OrderSMS, `.80`, remote per-store DBs) without requiring a single shared "master" database to coordinate from, since none exists today (doc 15 §1-2).
- Make "has tenant/store X received migration Y" answerable without a human manually connecting to each database.
- Preserve the current backward-compatibility discipline (item 7) as a hard requirement, not an afterthought — every migration must be additive/nullable-safe by default, matching `schema_evolution.py`'s `force_nullable=True` precedent.

### Proposed migration ID scheme
- Reuse the existing per-module numbered-file convention (`backend/modules/<module>/sql/NNNN_description.sql`) as the authoring format — developers already know it.
- Add a **global, monotonically increasing migration ID** independent of the per-module counter, e.g. a `YYYYMMDDHHMM_<module>_<slug>.sql` filename prefix (sortable, collision-resistant across modules without coordination), while keeping the existing per-module `NNNN_` prefix as a secondary human-readable label if desired. This avoids the current ambiguity where `procurement/sql/0013_min_order_flag.sql` and `procurement/sql/0013_network_intelligence.sql` already collide on the same number (observed in the file listing) because nothing currently enforces uniqueness.
- Every migration file states its own required companion: a `_verify.sql` (read-only check the migration applied correctly) is proposed as *mandatory* going forward, formalizing the pattern procurement's `0026`-`0030` series already started informally; `_rollback.sql` mandatory only for destructive or high-risk changes (additive nullable changes generally don't need one).

### Proposed migration tracking table (schema design only — not created)
A new table, e.g. `dbo.schema_migrations`, proposed to live in **every** application database this touches (platform DB on each HO, plus each legacy Order central DB OrderNMC/OrderSMS/OrderSuccess, plus remote per-store DBs if/when they take on their own tracked schema):
```
schema_migrations (
    migration_id      VARCHAR(100)  NOT NULL,   -- the YYYYMMDD..._slug id
    module            VARCHAR(100)  NOT NULL,
    applied_at        DATETIME2(0)  NOT NULL DEFAULT SYSUTCDATETIME(),
    applied_by_node   NVARCHAR(100) NULL,        -- which HO/backend instance ran it
    status            VARCHAR(20)   NOT NULL,     -- APPLIED | FAILED | ROLLED_BACK
    verify_passed     BIT           NULL,
    error_detail      NVARCHAR(MAX) NULL,
    CONSTRAINT PK_schema_migrations PRIMARY KEY (migration_id)
)
```
This directly fills the gap identified in item 6: today, nothing durable records "has migration Y been applied to database X." This table is the proposed answer — intentionally modeled closely on what tools like Alembic/Flyway track, but deliberately kept as a single plain table (no new framework dependency) so it fits the codebase's existing "small, explicit SQL, no ORM migration DSL" style.

### Proposed HQ-to-tenant control flow
1. A developer authors a new migration file under its owning module's `sql/` folder, following the ID scheme above, written to be additive/nullable per the backward-compat discipline already proven out in `schema_evolution.py`.
2. A new, thin orchestration layer (proposed name: `backend/modules/schema_sync` is extended, rather than a wholly new module, since it already has the super-admin-gated router pattern and target-connection model) gains a **registry of known target databases** — this is new: today `schema_sync` takes `source`/`target` purely as request payload with no stored list (doc 15 §4). Proposed: a new table `dbo.schema_sync_targets` (label, server, database, credentials-by-reference to the existing Fernet-encrypted credential pattern already used for store/license connections) that an operator populates once per known HO/tenant/store database, turning today's "type in two connections every time" workflow into a maintained inventory — closing part of the item-1/2 gap from doc 15 as a side effect.
3. The orchestrator iterates the target registry, and for each target: connects, checks `dbo.schema_migrations` for the highest `migration_id` already `APPLIED`, and runs any newer migration files in ID order — each wrapped in its own transaction/connection per the existing `schema_sync.apply()` best-effort-but-isolated-per-statement precedent (doc 15 cites `schema_sync/service.py:525-538`).
4. After each migration, the paired `_verify.sql` runs; its result is recorded in `verify_passed` before the row is marked `APPLIED`.
5. Failures are recorded as `FAILED` with `error_detail` and the orchestrator **continues to the next target** (same single-bad-statement-shouldn't-block-everything-else philosophy already proven in `schema_sync.apply()`) rather than aborting the whole multi-tenant rollout.

### Proposed retry / failure handling
- A `FAILED` row is retryable: re-running the orchestrator against that target re-attempts only migrations not already `APPLIED` there (idempotent by construction, since the underlying `.sql` files themselves remain `IF OBJECT_ID/COL_LENGTH IS NULL`-guarded as today).
- No automatic retry loop proposed (risk of hammering a genuinely broken target); instead, a dashboard/report (reusing existing HO-ops/device-controller UI patterns) surfaces "target X is N migrations behind" for an operator to re-trigger deliberately — echoing how `schema_sync`'s compare/apply today is explicitly an operator-initiated action, not a background job.

### Proposed rollback approach
- Default posture: **forward-only**, matching the existing codebase's near-total absence of destructive rollback tooling (only `schema_evolution.py`'s rare DROP+rebuild path, and even that is additive in effect — rebuilding into a *more* capable shape, never removing capability).
- For the rare migration that must be reversible, require the author to supply `_rollback.sql`; the orchestrator can mark a migration `ROLLED_BACK` and run that file, but rollback execution stays a manual, explicit operator action (never automatic), consistent with how `schema_sync` already treats all DDL changes as something a human reviews before `apply()`.

### Proposed tenant-by-tenant verification
- Reuse the existing `_verify.sql` convention (procurement's `0026`-`0030` precedent) uniformly: every migration ships one, and the orchestrator's per-target report is literally "ran verify, got pass/fail" per target — giving the owner a single view of "this schema change is confirmed live and correct on `.73`, pending on `.32`-SMS, failed verify on the OrderSuppliers remote DB for store Q" without manually connecting anywhere, directly closing the gap called out in item 6 above.

### Explicit non-goals of this proposal
- Not proposing to replace the per-module `ensure_schema()` self-healing idiom — it stays, as the inner mechanism each migration file still uses to be individually idempotent. This proposal only adds an outer layer that knows *which* targets exist and *whether* a given migration has reached each one.
- Not proposing any change to Device Controller — per doc 15 §4/5, it is confirmed to be an app-binary distribution tool with no DB awareness, and nothing here asks it to gain one; schema rollout stays a separate concern from binary rollout.
- Not proposing to touch `backend/modules/sync/schema_evolution.py`'s existing scope (the `sync.*` merge-table evolution) — it already does its narrow job correctly and would simply continue operating independently alongside this broader mechanism.

---

## Summary for the Phase 7C consolidation decision

Any new table/column the Legacy Order + Procurement Workspace consolidation needs, deployed today, would go out the same way every prior schema change in this codebase has: a new numbered `.sql` file, written additive/nullable-safe, optionally wired into an `ensure_schema()`-style self-apply at backend boot for automatic nodes, and manually run via `schema_sync` (or by hand) against every other known database (`.32`, `.80`, remote OrderNMC-family DBs) — with no durable record anywhere of which databases have actually received it. The proposed migration-tracking table and target registry above are offered as the natural, minimal-disruption extension of that existing discipline, not a replacement for it, should the owner choose to build it in a future phase.
