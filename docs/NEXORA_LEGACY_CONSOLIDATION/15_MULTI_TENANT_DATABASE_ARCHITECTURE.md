# 15 — Multi-Tenant Database Architecture (Existing, Verified)

Status: READ-ONLY investigation. No files, databases, or git state were modified while producing this document. Scope: items 1, 2, 4, 5 of the Phase 7C multi-tenant schema-change investigation brief.

Tag legend: **VERIFIED** (read directly in code, cited file:line) · **PARTIAL** (confirmed mechanism exists, some edge/scale detail not traced) · **INFERRED** (reasoned from verified facts, not directly read) · **UNKNOWN** (not found / out of scope to confirm without a live DB).

---

## 1. How many distinct "HO" deployments does the backend know about, and how does it pick a DB?

**VERIFIED — single global connection per backend process, resolved from environment, not from a tenant parameter.**

`backend/config/database.py:82-99` (`_connection_string()`) builds ONE pyodbc connection string from `DB_SERVER` / `DB_DATABASE` / `DB_DRIVER` / `DB_AUTH_MODE` / `DB_USERNAME` / `DB_PASSWORD` environment variables (defaults: `192.168.10.73`, `NEXORA_PLATFORM`). `get_connection()` (`database.py:102-131`) is the one function nearly every module (`backend/repositories/*.py`, most of `backend/modules/*/repository.py`) imports and calls for "the platform DB."

There is **no runtime tenant_id parameter on `get_connection()`**. The file's own docstring (`database.py:1-13`) states the design intent plainly: *"Connection parameters resolve from environment variables so the SAME backend works for any tenant. The HO installer writes them into `config\ho.env`."* In other words: **one backend deployment = one physical database**, selected once at process start by whichever `.env`/`ho.env` that machine was installed with. "Multi-tenant" (e.g. `.32` hosting SUCCESS + SMS) means multiple **logical tenants sharing that one physical `NEXORA_PLATFORM` database**, distinguished by a `tenant_id` column on rows — not multiple physical databases picked per request.

Known HO nodes per user memory (`.73` main HO, `.32` SUCCESS+SMS, `.80`) are therefore **three separate backend process deployments**, each with its own `config/ho.env`, each pointing at its own single `NEXORA_PLATFORM`-shaped database. The backend code has no built-in concept of "there are 3 HO nodes" — that inventory lives only in human/ops knowledge (memory notes, deployment runbooks), confirmed by the complete absence of any `HO_NODES` / `ho_registry` table or config listing all HO instances (see §2).

One deliberate exception exists: **licensing data** can be split per-tenant into a *dedicated* database — `backend/modules/licensing/db_resolver.py:1-17` — controlled by a `dbo.tenants.license_db_mode` column (`SHARED` default, `DEDICATED` opt-in). `get_license_connection(tenant_id)` (`db_resolver.py:77-83`) checks that flag and either returns the normal platform connection or opens a bespoke pyodbc connection built from `license_db_server/name/username/password_encrypted` columns on that tenant's row, decrypted with the store-agent's Fernet key (`db_resolver.py:58-69`). This is the **only** place in the codebase where a single backend process routes different tenants to genuinely different physical databases at request time. It is scoped narrowly to `tenant_licenses` / `tenant_usage_status` rows, not general application data.

## 2. Tenant / store discovery — is there a central registry?

**VERIFIED — yes, two tables inside the platform DB: `dbo.tenants` and `dbo.stores`. No registry of HO nodes/backends themselves.**

- `dbo.tenants` — columns `tenant_id, tenant_code, tenant_abbreviation, tenant_name, db_name, is_active, legacy_db_name` (`backend/repositories/tenant_repository.py:26-36`). `legacy_db_name` is a later addition (`tenant_repository.py:6-24`, added via an idempotent `ALTER TABLE ... ADD` guarded by an `INFORMATION_SCHEMA.COLUMNS` existence check) that lets an admin point a tenant's Legacy Order console at a specific central database (e.g. `OrderSMS`) from a Tenants admin screen, overriding the env-var mapping described below.
- `dbo.stores` — columns include `store_id, tenant_id, store_code, store_name, server_name, database_name, is_active, is_warehouse, store_order`, plus (per `get_agent_config`) `username, password_encrypted, connection_type, agent_version` (`backend/repositories/store_repository.py:11-69`). This is the actual **store → physical DB connection** registry: each store row carries its own `server_name`/`database_name`/credentials for the store-agent sync pipeline.

Both tables live only inside *that HO's own* `NEXORA_PLATFORM`-shaped database (per §1, there is no separate "master" database listing all HO nodes). So discovery is two-level:
  1. Within one HO deployment, `dbo.tenants` + `dbo.stores` tell you every tenant and store *that HO* serves, and how to reach each store's own database.
  2. Across HO deployments (`.73` vs `.32` vs `.80`), there is **no code-level registry at all** — VERIFIED by the complete absence of any table/model with a name like `ho_nodes`, `ho_registry`, `deployments`, etc. in `backend/models` or `backend/modules/*/sql/*.sql`. This inventory exists only as operator/memory knowledge.

For the **Legacy Order** console specifically, a second routing layer exists on top of `dbo.tenants`/`dbo.stores`: `backend/modules/legacy_order/database.py`. Its docstring (`database.py:1-18`) states it deliberately does **not** use `config.database` — it targets the OLD `OrderNMC` database (or its per-tenant siblings `OrderSMS`/`OrderSuccess`) and the branch SQL Servers those stores point at, mirroring the legacy VB.NET app's own connection logic.
  - `LEGACY_DB_DATABASE_BY_TENANT` env var: a `tenant_id=dbname;tenant_id=dbname` string (`database.py:62-74`), same pattern as `ordernmc_mirror`'s `ORDERNMC_MIRROR_SOURCES`.
  - `dbo.tenants.legacy_db_name` (read via `_tenant_legacy_db_name()`, 30s TTL cache, `database.py:274-296`) takes priority over the env-var map.
  - `set_active_tenant(tenant_id)` / `reset_active_tenant(token)` (`database.py:77-87`) use a `contextvars.ContextVar` to scope which central DB name (`_database_name()`, `database.py:298-307`) subsequent connections on that task resolve to. **Caveat verified in the same file**: contextvars do not cross a raw `threading.Thread` boundary, so every background thread spawned per-store MUST be wrapped with `tenant_scoped(store, fn)` (`database.py:89-105`) or it silently falls back to the default `OrderNMC` database regardless of the store's real tenant — a documented footgun, not a hypothetical one.
  - Branch-store credentials are **not** configuration at all — `database.py:16-17` states they're read per-store from the central DB's own `dbo.Stores` table (the legacy pattern inherited unchanged from the VB.NET app).
  - Ambiguous store-name collisions across tenants (same `store_code` under two tenants, e.g. `.32`'s two "SMA" stores) are resolved by checking `dbo.stores.tenant_id` in `NEXORA_PLATFORM` (`platform_store_id()`, `database.py:181-198`) — directly matches the memory note "Cross-tenant store scoping fix."

**HO route discovery (the "HO multi-URL" memory hint) — VERIFIED, found in `backend/modules/bootstrap/repository.py:1-60`.** Table `dbo.ho_routes` (`route_id, label, url, route_order, is_active, updated_at`) holds the ordered list of base URLs a store agent / desktop client tries, e.g. seeded with `LAN → http://192.168.10.73:8000`, `STATIC → http://122.252.246.181:8000`, `DOMAIN → https://ho.qvault.in` (`bootstrap/repository.py:16-20`). The docstring explains the intent directly: *"moving HO is a single UPDATE here rather than a reinstall on every store machine."* This is a **failover/discovery mechanism for reaching an HO's HTTP API**, not a database connection-string registry and not a list of other HO nodes — it is per-HO-deployment (each HO has its own `ho_routes` rows for itself).

## 3. Existing cross-database / cross-tenant sync mechanisms

**VERIFIED — several distinct, narrowly-scoped mechanisms; no single unified "sync everything" engine.**

- **`backend/modules/sync/*`** — the store-agent data-sync pipeline (catalog, table registry/master, column mapping, scheduler, runtime, health monitor, file-transfer transports including SFTP/email/file-drop). This replicates *store operational data* (sales, stock, batches, etc.) from each store's own SQL Server into the HO's `sync.*` schema. It is the pipeline that `schema_evolution.py` (next section) exists to support.
- **`backend/modules/ordernmc_mirror/*`** — a one-way HO→remote mirror of OrderNMC-shaped data, per user memory confirmed by directory presence (`repository.py`, `service.py` both exist and both contain `COL_LENGTH`/`OBJECT_ID` guards per the earlier grep). Matches memory note "OrderNMC mirror — HO→remote one-way mirror."
- **`backend/modules/schema_sync/*`** — **a manual, operator-triggered Dev→Production schema diff-and-apply tool**, not an automated sync. Full detail in doc 16 §"Existing." In short: `service.compare(source_conn, target_conn)` (`schema_sync/service.py:178-523`) snapshots both a Dev (source) and Production/HO (target) SQL Server via `repository.fetch_snapshot`, computes additive-only table/column/index/constraint/programmable-object diffs, and returns a list of `PlannedStatement`s for a human to review before calling `service.apply()` (`schema_sync/service.py:525-538`) — which runs each statement independently/best-effort (autocommit, continues past individual failures) and reports per-statement success/failure back to the caller. The router (`schema_sync/router.py:1-58`) is gated `require_super_admin` and takes `source`/`target` connection details **as request payload at call time** — confirming there is no stored registry of "all tenant DBs to sync to"; the operator supplies the target each time. This directly matches and VERIFIES the memory note "Schema sync .73→.32 — 2026-11-03 MANUAL schema-only sync."
- **`backend/modules/sync/schema_evolution.py`** — a real **automated**, idempotent per-table schema-evolution routine, but scoped *only* to the shared `sync.*` tables the store-sync merge pipeline writes into (full detail in doc 16).
- **`backend/modules/nmv_integration/*`** — remote-store agent integration over outbound HTTPS (per memory, inverts the normal LAN direction: remote stores reach HO over the internet rather than HO reaching into a LAN). Has its own numbered SQL files (`sql/0001_nmv_integration.sql`, `sql/0002_nmv_enrollment_code.sql`) — same ad-hoc per-module pattern as everywhere else, confirmed by directory listing.

**No code was found that automatically propagates a schema change from one HO's database to another HO's database.** `schema_sync` requires a human to open the tool and explicitly point it at two live connections; nothing scans `.73`, `.32`, `.80` and reconciles them together or on a schedule.

## 4. Device Controller / remote update mechanism — what does it actually update?

**VERIFIED — application binaries/packages, NOT database schema.**

`backend/modules/device_controller/packages.py:1-29` docstring: *"Package catalog for controller-driven installs/updates... Each HO node scans its own release folders and registers what it holds in `dbo.dc_packages`."* `RELEASE_ROOTS` (`packages.py:24-29`) maps `app_key` → local folder:
```
ho_backend  -> backend/ho_backend_releases
stock_client -> backend/stock_client_releases
store_agent  -> backend/agent_releases
controller   -> backend/device_controller_releases
```
Every one of those is a folder of **release archives/binaries** (matches the on-disk directories actually present: `backend/ho_backend_releases`, `backend/stock_client_releases`, `backend/agent_releases`, `backend/device_controller_releases` all exist per the earlier directory listing). `self_base_url()` (`packages.py:36-51`) lets each HO node advertise where its own release files can be downloaded from (LAN IP or `NEXORA_SELF_URL` override) — i.e. the mechanism for *distributing an update package*, not for running DDL.

`backend/modules/device_controller/service.py:1-96` confirms the runtime surface: signed commands, a long-poll device inbox, remote terminal sessions, enrollment, and the package catalog (`list_packages()` at line 100) — all application/OS-level device-management primitives (matches memory: "SYSTEM service replacing all watchdogs," remote terminal access). **Nothing in this module issues SQL or touches a tenant's application database schema.** The "HO backend remote update" and "Stock Client fleet ops" memory notes are consistent with this: Device Controller pushes a *new backend/agent binary* to a node and (presumably, by restarting the service) that new binary's own `app.py`-level `ensure_schema()` calls then self-heal that node's database schema on the next boot (see doc 16 for exactly what those calls do and don't cover). Device Controller itself has no DB-migration awareness.

## Identified gaps (carried forward into doc 16 as the "primary finding")

1. **No registry of HO deployments.** `dbo.tenants`/`dbo.stores` only describe tenants/stores *within* one HO's own database. Which physical servers/databases constitute `.73`, `.32`, `.80` is operator knowledge only — not queryable from any one backend.
2. **No tenant-aware schema migration system.** Schema changes propagate via (a) best-effort `ensure_schema()` calls that run automatically but silently swallow failures at import time, (b) per-module numbered `.sql` files that are sometimes auto-applied once-per-process (no persisted version tracking) and sometimes are pure documentation for a human to run by hand, and (c) the manual `schema_sync` Dev→Prod diff tool that requires an operator to explicitly target each database, one at a time, with no multi-target/fan-out capability. None of these three together constitute an automated, versioned, "push once, apply everywhere" mechanism across `.73`/`.32`/`.80`/remote-store DBs.
3. **Device Controller cannot deploy schema changes.** It is purely an app-binary/package distribution and remote-terminal tool. A future requirement to "deploy a schema change safely to all tenant databases" has no existing hook into Device Controller's command/package model — it would need new design, not reuse.

See doc **16_SCHEMA_MIGRATION_AND_ALL_TENANT_DEPLOYMENT_PLAN.md** for the full schema-versioning findings (item 3), the honest current-state assessment (item 6), the backward-compatibility evidence (item 7), and a clearly-labeled PROPOSED (not implemented) future design.
