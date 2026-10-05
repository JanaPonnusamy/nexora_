# NEXORA — Technical Detail Reference

Deep reference. Read `PROJECT.md` first for orientation. This file follows
the audit/implementation done for the FILE_TRANSFER sync feature; sections
are grouped by the audit phases used to build it.

---

## 1. Repository structure (top level, noise excluded)

```
backend/            HO FastAPI app (api/, controllers/, modules/, repositories/, tests/)
frontend/            HO React/Vite/Electron SPA (src/pages, src/routes, src/components)
store_agent/         Per-store sync/runtime service (production entry: run_agent.py)
store_agent_setup/    Store Agent installer wizard + Settings + Watchdog
ho_setup/             HO installer builder (-> release/HO_Setup.exe)
desktop/supplier-stock-client/   Standalone Electron app (Stock/Analysis/NMW)
mobile/               Flutter app, talks to backend/modules/mobile_bff
installer/            Legacy phased installer scripts; installer/sql/ = foundational DDL
automation/           Repo tooling CLI (python -m automation ...)
docs/                 Design docs, ADRs, business rules, SYNC-0xx narrative docs
tests/                Store-agent/sync/procurement pure-Python test suite (flat, ~90 files)
```

## 2. Application architecture

**HO Backend** (`backend/api/app.py`): one FastAPI app, ~40+
`include_router()` calls, one router set per module under
`backend/modules/*`. Auth is a middleware gate (`require_auth`) with a
regex allowlist for the unauthenticated store-agent-facing sync endpoints
(`/api/sync/tasks/*`, `/api/sync/chunks/*`, `/api/sync/configuration/*`,
`/api/sync/tables/report`, `/api/sync/schema/register`) — these predate JWT
auth and are called by an unattended service with no user session.

**HO Frontend** (`frontend/src/routes/AppRouter.tsx`): lazy-loaded routes
under capability-gated groups (`/platform/*`, `/sync/*`, `/procurement/*`,
`/product-mapping`, `/label-exporter`, etc.), wrapped by `AppShell` layout.

**Store Agent**: packaged via PyInstaller (`NexoraStoreAgent.spec` etc.),
runs as Windows service `NexoraStoreAgent`, watched by a separate Watchdog
service. **`store_agent/main.py` and `store_agent/runtime/*` (RuntimeHost,
runtime_scheduler.py) are earlier-generation scaffolding not used in
production** — the real entrypoint is `store_agent/run_agent.py`.

## 3-5. HO / Store / Electron application detail

Covered at the index level in `PROJECT_INDEX.md` (screens, routes, APIs).
Not re-derived here beyond what the sync work touched.

## 6. Store Agent — modules relevant to sync

| Concern | Files |
|---|---|
| Identity/config | `config.py` (multi-URL failover), `agent_config.json` (deployed per store) |
| SQL connection | `sql_connection_factory.py`, `runtime_sql_connection_service.py` |
| Schema discovery/catalog | `schema_scanner.py`, `catalog/*`, `schema_classification_*` |
| **DIRECT_HTTP sync engine** | `services/sync_runtime_orchestrator.py` (orchestration), `services/data_extraction_service.py`, `services/hash_generation_service.py`, `services/chunk_builder_service.py`, `services/sqlite_cache_service.py` (local durable cache + outbox) |
| **DIRECT_HTTP transport** | `services/task_polling_service.py`, `services/catalog_sync_service.py`, `services/sync_sender_service.py`, `services/sync_ack_processor.py` — four thin `requests`-based clients |
| **FILE_TRANSFER (new)** | `file_transfer/` package + `services/file_transfer_runtime_orchestrator.py` — see §31 |
| Entrypoint | `run_agent.py` (heartbeat loop + sync-or-file-transfer loop) |

## 7. Backend architecture (sync module)

`backend/modules/sync/` — largest module besides procurement:

| File | Purpose |
|---|---|
| `runtime_router.py` / `runtime_repository.py` / `runtime_service.py` | The live DIRECT_HTTP protocol: task create/poll/start/complete/fail, configuration download, chunk upload+ack, table metrics, live status |
| `scheduler_service.py` / `scheduler_repository.py` / `scheduler_time.py` | HO-side periodic tick (30s) that reads `dbo.sync_schedule`, claims per-store execution slots via `sp_getapplock`, enforces max concurrency |
| `schema_evolution.py` | Dynamically creates/alters `sync.<table>` shared tables from `sync.sync_column_mapping` |
| `catalog_repository.py` / `catalog_router.py` / `catalog_service.py` | Store schema catalog upload/browse |
| `table_master_*`, `table_registry_*`, `column_mapping_*` | Admin CRUD for which tables/columns sync |
| `shared_table_builder_*` | One-time DDL promotion tooling |
| **`file_transfer_repository.py`, `file_transfer_validator.py`, `file_transfer_receiver_service.py`, `file_transfer_scheduler.py`, `file_transfer_config.py`, `file_transfer_transport/`** | New FILE_TRANSFER receiver pipeline — see §31-33 |

## 8-12. Frontend / DB / Auth (unchanged by this task)

No frontend or authentication changes were made. Database schema additions
are limited to one new table, `sync.file_sync_packages` (§34).

## 13. Sync architecture — DIRECT_HTTP (existing, audited, unmodified)

```
Store Agent (run_agent.py, 60s loop)
  1. flush_pending()            -- resend any chunk still in SQLite outbox
  2. poll  GET /api/sync/tasks/pending/{store_id}
  3. per pending task:
     start POST /api/sync/tasks/{id}/start
     config GET /api/sync/configuration/{id}   -> table/column list (HO is
                                                    single source of truth)
     per table:
       extract (watermark or full scan per sync_mode)
       diff (row SHA-256 hash vs SQLite sync_row_cache, or watermark column)
       chunk (1000 rows/chunk)
       queue_chunk() into SQLite sync_pending_chunks (durable outbox)
       POST /api/sync/chunks/upload  -> HO stages into #stage temp table,
                                          MERGEs into sync.<table> keyed
                                          (store_id, business PK)
       POST /api/sync/chunks/ack
       POST /api/sync/tables/report  (per-table metrics/status)
     complete POST /api/sync/tasks/{id}/complete
```

Identification is `store_id` embedded in every payload body (no API
key/JWT on this surface — see §35 Security). Tenant/store context for a
chunk is derived server-side from `dbo.sync_execution`, never trusted from
the request. Failure isolation: per-table (`run_table_safe`), per-cycle
(heartbeat/sync loops never die), per-chunk (`upload_chunk` rolls back and
records a `FAILED` row with a diagnosed bad-column detail on bulk-insert
failure). Durable state: SQLite (`sync_row_cache`, `sync_table_state`,
`sync_pending_chunks`) on the agent; `dbo.sync_execution`,
`dbo.sync_chunk_execution`, `dbo.sync_execution_details`,
`dbo.sync_execution_audit`, `sync.sync_table_progress` at HO.

## 14-17. Sync tables / configuration / scheduling / polling

- `sync.sync_table_master` / `sync.sync_column_mapping` — what/how to sync,
  admin-editable, HO is authoritative.
- `dbo.sync_schedule` — per-tenant interval (default 30 min), read by
  `scheduler_service.py`'s 30s tick.
- `dbo.sync_execution` / `dbo.sync_chunk_execution` — the run + chunk
  ledger both DIRECT_HTTP and FILE_TRANSFER write into (FILE_TRANSFER rows
  are tagged `execution_type = 'FILE_TRANSFER'`).
- Agent polling: `GET /api/sync/tasks/pending/{store_id}` every cycle.

## 18-20. Procurement / VPL / Supplier workflow

Unchanged by this task. See `docs/Procurement_*`, `docs/BUSINESS_RULES/`,
and `[[procurement-schema-rulings]]`-style prior work (not re-derived here).
`decision_rules.py` / `decision_service.py` were not opened for editing.

## 21-30. Reports / APIs / background services / logging / deployment / build / testing

Unchanged. See `PROJECT_INDEX.md` §7-8 for the module/report inventory and
§18 for build/deploy scripts.

## 29. Existing problems found during this audit (not fixed — out of scope)

- `store_agent/main.py` and `store_agent/runtime/*` are dead/superseded
  code paths from an earlier build generation; the real service is wired
  through `run_agent.py`. Left as-is (out of scope; flagged for a future
  cleanup pass).
- `tests/test_table_creation_engine.py`,
  `tests/test_schema_sync_engine.py`, and
  `tests/test_store_agent_config_contract.py` were already failing before
  this task (stale APIs referencing removed/renamed methods). Verified via
  `git status`/code inspection that this task did not touch any of the
  files involved; left unfixed as pre-existing, unrelated breakage.

## 30. Architecture constraints honored

- DIRECT_HTTP transport, protocol, and merge logic: byte-for-byte
  unmodified (verified: existing sync/store-agent test suite green, see
  final report).
- `decision_rules.py` / `decision_service.py`: not opened for editing.
- SQL Server 2014 compatibility: the new migration
  (`backend/modules/sync/sql/0001_file_sync_packages.sql`) uses only
  `UNIQUEIDENTIFIER`, `VARCHAR`, `NVARCHAR`, `DATETIME`, `INT` and
  `IF OBJECT_ID(...) IS NULL` guards — no `STRING_AGG`, no native JSON type,
  matching the same idiom as
  `backend/modules/procurement/sql/0024_product_network_movement.sql`.

---

## 31. File Transfer Sync — design

```
Store SQL Server
   |
   v
DataExtractionService / HashGenerationService / ChunkBuilderService
   (store_agent/services/*.py -- REUSED VERBATIM from DIRECT_HTTP,
    via FileTransferRuntimeOrchestrator, which also calls
    SyncRuntimeOrchestrator._hash_columns / ._pk_value directly rather
    than reimplementing them)
   |
   v
PackageBuilder (store_agent/file_transfer/package_builder.py)
   -> one ZIP per cycle: manifest.json + payload/<table>__<chunk>.json + checksums.json
   |
   v
FileTransferOutbox (store_agent/file_transfer/outbox.py)
   -> SQLite file_sync_packages: CREATED -> SENDING -> SENT -> ACKNOWLEDGED
                                              \-> FAILED (retried next cycle)
   |
   v
Transport adapter (store_agent/file_transfer/transport_factory.py)
   FILE_DROP (file_drop_transport.py) | SFTP (sftp_transport.py, paramiko)
   | EMAIL (email_transport.py, smtplib+imaplib, stdlib only)
   |
   v
HO Receiver Transport (backend/modules/sync/file_transfer_transport/*.py
   -- independently implemented mirror of the same 3 modes; backend and
   store_agent are separate deployables and never share a Python runtime)
   |
   v
file_transfer_receiver_service.run_tick()
   RECEIVE -> extract (path-traversal + size guarded)
           -> VERIFY CHECKSUM (checksums.json vs actual sha256)
           -> VALIDATE MANIFEST (required keys, sync_mode, payload files exist)
           -> VALIDATE STORE (dbo.stores lookup), resolve tenant if absent
           -> CHECK DUPLICATE (sync.file_sync_packages by checksum, then by package_id)
           -> STAGE/MERGE (per table: runtime_repository.upload_chunk(),
                            the SAME staging+MERGE code DIRECT_HTTP chunks use)
           -> COMMIT (report_table_metrics + complete_task/fail_task,
                       same calls DIRECT_HTTP makes)
           -> ACKNOWLEDGE (result .json sent back over the same transport)
```

**Why one engine, not three**: the "sync engine" -- what changed, how much,
in what shape -- is entirely `DataExtractionService` +
`HashGenerationService` + `ChunkBuilderService` +
`SqliteCacheService`/`runtime_repository.upload_chunk`. Those are imported
and called directly by the FILE_TRANSFER orchestrator/repository, not
reimplemented. The only new code is: (a) how a cycle's output is grouped
(one package instead of N live HTTP calls) and (b) how the package
physically moves (a transport adapter instead of `requests`).

**Deliberate scope reduction vs. DIRECT_HTTP** (documented, not hidden):
the `ProductSaleInformation`/`SaleInformation` linked-cursor extraction
optimization and per-table `source_max` verification logging in
`SyncRuntimeOrchestrator` are DIRECT_HTTP-only observability/performance
refinements, not correctness rules, and are not reproduced in
`FileTransferRuntimeOrchestrator`. Every table still gets a full, correct
hash/watermark diff.

## 32. HO Import Pipeline

Implemented in `file_transfer_receiver_service.py` +
`file_transfer_repository.py` + `file_transfer_validator.py`. Per-table
isolation mirrors the agent's `run_table_safe`: one table's staging/merge
exception is caught, recorded via `report_table_metrics(status='FAILED',
error_message=...)`, and the loop continues to the next table. The whole
package is only marked `FAILED` if every table in it failed; otherwise
`complete_task()` runs and the execution shows as `COMPLETED` in every
existing HO screen (Live Operations, Table Statistics, sync history) --
FILE_TRANSFER executions are indistinguishable from DIRECT_HTTP ones there
except for `execution_type = 'FILE_TRANSFER'`.

## 33. Retry / Recovery

- **Agent side**: a package stuck in `CREATED`/`FAILED` is retried by
  `FileTransferOutbox.due_for_send()` on the next cycle; a transport
  failure mid-send stops the rest of that cycle's send attempts (mirrors
  `SyncRuntimeOrchestrator.flush_pending()`'s `break`-on-failure), so a
  down transport degrades to "retry next cycle," never a crash loop.
- **HO side**: FILE_DROP/SFTP leave an unimportable package in the inbox
  (not archived) on a transient `FAILED` outcome, so the next tick retries
  validation+import from scratch; only `REJECTED` (permanently invalid)
  packages are quarantined. The EMAIL receiver now follows the same
  contract: `\Seen` is set only in `archive_incoming()`, which
  `file_transfer_receiver_service._import_one` calls solely for terminal
  outcomes (imported / duplicate / rejected / a post-validation import
  failure) -- a transient validation-stage `FAILED` never calls it, so that
  message stays unseen and the next `UNSEEN` poll retries it automatically.
  (Previously fixed known limitation: `list_incoming()` used to mark every
  fetched message `\Seen` unconditionally, before the outcome was known,
  which silently defeated retry for every failed email package. Fixed in
  `backend/modules/sync/file_transfer_transport/email.py` and mirrored on
  the store side in `store_agent/file_transfer/email_transport.py`, where
  `remove_result()` was previously a no-op documented as "already marked
  \Seen" but never actually marked anything -- ACK results were re-fetched
  and re-processed every cycle indefinitely, harmless only because
  `mark_package_acknowledged` is idempotent.) Both sides also now enforce an
  optional `max_attachment_bytes` before sending a package, raising
  `PACKAGE_TOO_LARGE` instead of attempting a broken/oversized send -- the
  package stays durably `FAILED` in the outbox for operator intervention.
- **Fallback**: FILE_TRANSFER is opt-in per store; a store can always be
  reverted to DIRECT_HTTP (see rollback steps in the final report) if its
  connectivity profile changes.

## 34. Idempotency

`sync.file_sync_packages.package_id` (the store-generated execution_id) is
the primary key; `checksum` (sha256 of the .zip) carries a separate unique
index. A replayed package -- the same physical file re-picked-up after a
crash, a retried email, an operator re-dropping a file -- is caught two
ways: (1) a pre-check (`find_by_checksum`/`find_by_id`) before any import
work starts, short-circuiting to a clean `DUPLICATE` outcome, and (2) the
database's own unique constraints as a race-condition safety net if two
receiver processes somehow picked up the same file concurrently.
Independently, `dbo.sync_execution.execution_id` (== the package_id) being
a primary key means even a bypass of the package-level check would still
fail at `INSERT INTO dbo.sync_execution` rather than double-import.

## 35. Security

- **Checksums**: every package carries a `checksums.json` verified before
  any content is trusted (independent of whatever integrity guarantee the
  transport itself provides).
- **ZIP extraction**: every archive member's path is normalized and
  checked against the extraction root before being written
  (`file_transfer_validator._safe_member_path`) -- rejects absolute paths,
  drive-letter paths, and `../` traversal. Per-member and whole-package
  size caps (100MB / 200MB) guard against a decompression-bomb-style
  resource exhaustion. Nothing extracted from a package is ever executed.
- **Credentials**: SFTP (`password_env`/`key_password_env`) and
  SMTP/IMAP (`password_env`) secrets are always environment-variable
  *references* in config, never embedded values -- consistent with how the
  rest of this backend reads secrets (`os.getenv`, see
  `scheduler_service.py`). Nothing new was hardcoded.
- **Tenant/store isolation**: a package's `store_id` is validated against
  `dbo.stores` before any row is imported; `tenant_id` is resolved
  server-side from `dbo.stores` if the manifest didn't carry one (same
  fallback `agent_heartbeat()` already uses). The actual MERGE step
  (`runtime_repository.upload_chunk`) keys every row on
  `(store_id, business PK)` exactly as DIRECT_HTTP does -- no new isolation
  logic was needed there.
- **Known gap carried over from DIRECT_HTTP, not introduced here**: the
  DIRECT_HTTP sync HTTP surface has no API key/JWT at all (trust-the-network
  model). FILE_TRANSFER is arguably *more* exposed if a transport
  credential leaks (an internet-reachable SFTP/mailbox vs. a LAN-only HTTP
  endpoint), which is exactly why FILE_TRANSFER package identity is
  validated against `dbo.stores` and checksummed end-to-end, unlike the
  DIRECT_HTTP chunk endpoints which currently trust `store_id` in the body
  outright. A future improvement (out of scope here) would be adding
  per-store transport credentials/signing; today all stores sharing one
  FILE_DROP/SFTP/mailbox implicitly trust each other's manifests to name
  their own real `store_id`, mitigated by the `dbo.stores` existence check
  and per-table MERGE keying but not by cryptographic signing.

## 36. Operational procedures

See the final implementation report for exact enable/disable steps for
both `DIRECT_HTTP` and `FILE_TRANSFER`.

## 37. Phase 2 extraction: standalone EMAIL delivery/receiving processes

Scope: EMAIL transport only. FILE_DROP and SFTP are completely unaffected by
everything in this section -- they still build and deliver inside the main
agent/backend process, exactly as before.

**Why:** running SMTP/IMAP inline inside the main Store Agent / HO backend
process means a mail-server outage or a slow IMAP poll can stall the process
that also owns SQL extraction (store) or the API (HO). Extracting delivery
and receiving into their own always-on processes means a mail outage only
ever blocks mail; sync extraction and the HO API keep running.

**Non-negotiable constraint honoured:** no new sync/receive engine was
written. `store_agent/mail_transfer_main.py` is a new *host* for the
existing `FileTransferSyncDispatcher._flush_pending`/`_process_results`
logic (exposed via the new `FileTransferSyncDispatcher.run_delivery_only()`
method -- `run()` is untouched and still used by FILE_DROP/SFTP).
`backend/mail_receiver_main.py` is a new *host* for the existing
`modules.sync.file_transfer_scheduler.run_forever()` loop (renamed from a
private `_loop()`, behaviourally identical, now also driveable outside a
background thread). Neither file reimplements SMTP, IMAP, checksum
validation, manifest parsing, staging, or MERGE.

**Store side** (`store_agent/mail_transfer_main.py`, packaged as
`NexoraMailTransfer.exe` via `store_agent_setup.build.build_mail_transfer()`,
hosted by `store_agent_setup/mail_transfer_service.py`):
- `run_agent.py::_run_file_transfer_cycle` now branches on
  `transport.mode`: for `EMAIL` it calls
  `FileTransferRuntimeOrchestrator.run_cycle()` directly (build only, never
  constructs a sender transport or a dispatcher); for everything else it
  keeps calling `FileTransferSyncDispatcher(...).run()` (build + deliver in
  one call, unchanged).
- The standalone process resolves the SAME `SqliteCacheService` (WAL mode,
  30s busy timeout, safe for concurrent multi-process access -- see
  `SqliteCacheService._connect`) and the SAME `FileTransferOutbox` root the
  main agent process uses, via the SAME `NEXORA_INSTALL_PATH`-anchored
  resolution. Two processes, one database, no new state.
- Polls on `file_transfer.mail_transfer_interval_seconds`
  (`NEXORA_MAIL_TRANSFER_INTERVAL_SECONDS` env override), independent of and
  normally much shorter than `interval_seconds` (which governs how often the
  main process builds a package).
- Refuses to do anything (logs and returns, never crashes the service loop)
  if `transport.mode != EMAIL` -- it is not a general-purpose delivery host.

**HO side** (`backend/mail_receiver_main.py`, packaged as
`NexoraHOMailReceiver.exe` via `ho_setup.build` / `ho_setup/HO_MailReceiver.spec`,
hosted by `ho_setup/mail_receiver_service.py`):
- `modules.sync.file_transfer_scheduler.start_background_loop()` now refuses
  to start the in-process thread when `transport_config().mode == "EMAIL"`
  (logs and returns `None`) -- EMAIL polling becomes the standalone
  process's exclusive job, so there is never a second process racing the
  first over the same mailbox's UNSEEN messages. FILE_DROP/SFTP still start
  the in-process thread exactly as before.
- `ho_setup/service_manager.ServiceManager` was parameterized (service_name/
  display_name/exe_name/module_name/description, all defaulting to the
  existing `UniNexHO` values) so a second HO Windows service doesn't need a
  second copy of the class -- mirrors the parameterization
  `store_agent_setup.service_manager.ServiceManager` already had for
  `NexoraStoreAgentWatchdog`.

**Config UI** (both opt-in, neither part of the default wizard flow since
most deployments never touch FILE_TRANSFER):
- Store: `store_agent_setup/settings_app.py` gained a "Mail Transfer"
  section (SMTP/IMAP host/port/folder, username, `password_env` name, HO
  address, max attachment size, Test SMTP/Test IMAP buttons that make a real
  connection, Install/Start/Stop for the `NexoraMailTransfer` service).
  Saving only ever writes `agent_config.json`'s `file_transfer` block when
  "Mail Enabled" is checked -- it never clobbers an existing FILE_DROP/SFTP
  config just because the checkbox is unticked.
- HO: `/api/sync/file-transfer/mail-config` (GET, view) +
  `/mail-config/test-smtp` / `/mail-config/test-imap` (POST, real connection
  attempts) on the existing `file_transfer_admin_controller.py`, surfaced at
  `frontend/src/pages/sync/SyncMailTransferPage.tsx`
  (`/sync/mail-transfer`). Deliberately **view + test only, no Save**: HO's
  FILE_TRANSFER config is plain environment variables by existing design
  (`file_transfer_config.py`'s own docstring: "not a new settings system")
  -- this UI honours that decision rather than introducing a second,
  competing config store for the same values. Passwords are never returned
  by the API, only whether the named `password_env` variable is set.

**Retry fix reused, not reintroduced:** the `\Seen`-on-terminal-outcome-only
contract from the earlier email-retry fix (§33) is what makes it safe for
the standalone receiver to be the sole poller -- a transient failure leaves
the message unseen for its own next poll to retry, with no second process
involved.
