# NEXORA — Project Memory

Permanent, concise reference. For depth see `PROJECT_DETAIL.md`; for a
navigable map of screens/APIs/tables see `PROJECT_INDEX.md`.

## Operational conventions

- **Always use PowerShell in ADMIN (elevated) mode for HO ops.** The default
  session is non-elevated; restarting the backend (SYSTEM `NexoraBackend` task /
  killing `:8000`), creating scheduled tasks, or setting the system clock all
  require elevation (non-elevated gets `Access is denied`). Self-elevate with
  `Start-Process powershell -Verb RunAs -ArgumentList '-File','<script>'` (approve
  the UAC prompt), or run the command in an Administrator PowerShell window.
- Restart the `.80` backend after a backend code change:
  `scratchpad\restart_80.ps1` (elevated) — kills `:8000`, re-runs the SYSTEM
  `NexoraBackend` task (loads `start-prod-8000.bat`), health-checks, logs to
  `backend\logs\ho_restart.log`. Backend-only Python changes need no frontend
  rebuild / pip install unless deps or `frontend/` changed.
- Exe nodes `.73`/`.32` update via a published release (Backend Update UI) or
  `ho_setup/node_ops/update_ho_node.ps1`, not a git restart.

## What is Nexora?

A multi-tenant retail/pharmacy platform: a Head Office (HO) admin system
(procurement, reporting, product mapping, label printing, WhatsApp, document
extraction, time/attendance) fed by data synchronized from each store's own
POS SQL Server database via a per-store **Store Agent**.

## Applications

| App | Where | Tech |
|---|---|---|
| HO Backend | `backend/` | FastAPI + pyodbc/SQL Server, `backend/api/app.py` |
| HO Frontend | `frontend/` | React 19 + Vite + TS, optional Electron shell |
| Store Agent | `store_agent/` | Python Windows service on each store PC |
| Store Agent Setup | `store_agent_setup/` | Installer wizard + Settings + Watchdog |
| Desktop Supplier-Stock Client | `desktop/supplier-stock-client/` | Standalone Electron app |
| Mobile | `mobile/` | Flutter, talks to `backend/modules/mobile_bff` |
| HO Setup | `ho_setup/` | Builds `HO_Setup.exe` (Inno Setup) |
| Automation CLI | `automation/` | Repo tooling (`python -m automation ...`) |

## How they communicate

- Frontend/Mobile/Desktop clients -> HO Backend: HTTPS REST, JWT auth.
- **Store Agent -> HO: two transport modes now (this task added the second).**
  1. **DIRECT_HTTP** (existing, default): unauthenticated REST over
     LAN/domain/static-IP, with automatic multi-URL failover
     (`store_agent/config.py`, `store_agent/HO_URLS.md`).
  2. **FILE_TRANSFER** (new, additive, opt-in): for stores with normal
     internet access but no route to HO's HTTP endpoint (no domain, no LAN,
     no public IP). A single checksummed ZIP package per cycle is moved
     through a pluggable transport (file-drop folder / SFTP / authenticated
     email) instead of live HTTP calls. See "New file-transfer architecture"
     below.

## Databases

One SQL Server 2014-compatible database, `NEXORA_PLATFORM`, several schemas:
- `dbo` — platform/legacy tables (tenants, stores, users, sync execution
  ledger, product mapping, label review, ...).
- `procurement` — procurement's own tables (cycles, VPL, supplier data,
  distribution, network movement).
- `sync` — the mirror of each store's POS data (`sync.Products`,
  `sync.ProductTrans`, `sync.PurchaseTrans`, ...), plus sync metadata
  (`sync.sync_table_master`, `sync.sync_column_mapping`,
  `sync.sync_schema_catalog`, and now `sync.file_sync_packages`).

`sync.*` business-data tables are created dynamically at runtime by HO's
schema-evolution code (`backend/modules/sync/schema_evolution.py`), not by
static migrations. Everything else follows
`backend/modules/<module>/sql/NNNN_description.sql`, applied idempotently via
each module's own `ensure_schema()` (self-provisioning on first use — no
external migration runner).

## Store Agent

Per-store Windows service. **Live production entrypoint is
`store_agent/run_agent.py`** — `store_agent/main.py` /
`store_agent/runtime/*` are earlier-generation stub code, not what's
actually running. Two independent loops:
- heartbeat (30s) — keeps the store marked ONLINE at HO.
- sync (60s, DIRECT_HTTP) **or** file-transfer (~30min, FILE_TRANSFER) —
  mutually exclusive, selected by `agent_config.json["file_transfer"]
  ["enabled"]`. A store runs exactly one sync engine at a time.

## How synchronization works (DIRECT_HTTP, unchanged by this task)

Table/column selection lives at HO (`sync.sync_table_master` /
`sync.sync_column_mapping`), downloaded once per task and cached locally.
Master tables diff by per-row SHA-256 hash against a local SQLite cache;
transactional tables diff by watermark column. Changed rows are chunked
(1000/rows) and POSTed to `/api/sync/chunks/upload`, which stages into a
temp table then `MERGE`s into `sync.<table>` keyed on `(store_id, business
PK)`. Full detail: `PROJECT_DETAIL.md` §13.

## New file-transfer architecture (this task)

```
Store SQL Server -> DataExtractionService/HashGenerationService/
ChunkBuilderService (SAME engine DIRECT_HTTP uses)
    -> PackageBuilder (ONE zip: manifest.json + payload/*.json + checksums.json)
    -> FileTransferOutbox (SQLite-tracked CREATED/SENDING/SENT/FAILED/ACKNOWLEDGED)
    -> Transport adapter (FILE_DROP | SFTP | EMAIL)
    -> HO Receiver (validate checksum/manifest/store -> idempotency check via
       sync.file_sync_packages -> per-table replay through the EXISTING
       runtime_repository.upload_chunk() MERGE engine -> result file back)
```

No second sync engine was created: extraction, hashing, chunking, and the
HO-side staging/MERGE logic are the exact same code DIRECT_HTTP uses. Only
the "how do changed rows physically reach HO" step differs. See
`store_agent/file_transfer/`, `store_agent/services/
file_transfer_runtime_orchestrator.py`, `backend/modules/sync/
file_transfer_*`.

## Phase 2: EMAIL transport extraction (standalone mail services)

For `transport.mode = EMAIL` only, package *delivery* (SMTP send + IMAP ACK
poll) and *receiving* (IMAP poll + validate/import + ACK send) each run as
their own standalone, separately-installed Windows service/process instead
of inside the main Store Agent / HO backend process:

- Store: `store_agent/mail_transfer_main.py` (packaged as
  `NexoraMailTransfer.exe`) sends whatever the main agent process already
  built into the shared SQLite outbox and polls for ACKs. The main agent
  process (`run_agent.py`) still builds packages every cycle, but for EMAIL
  mode it stops there -- it never opens an SMTP/IMAP connection itself.
- HO: `backend/mail_receiver_main.py` (packaged as
  `NexoraHOMailReceiver.exe`) hosts the exact same
  `modules.sync.file_transfer_scheduler.run_forever()` poll loop the FastAPI
  process would otherwise run in a background thread -- for EMAIL mode that
  in-process thread is now skipped (`file_transfer_scheduler.
  start_background_loop()` self-gates) so there is never more than one
  process polling the same mailbox.

FILE_DROP and SFTP are unaffected: both still build AND deliver inside the
main agent/backend process, exactly as before Phase 2. No receiving/sending
logic was duplicated -- the standalone processes are new *hosts* for the
existing EMAIL transport code, not a second implementation of it. See
`PROJECT_DETAIL.md` "Phase 2 extraction" for the full breakdown.

## Procurement (do not casually touch)

`backend/modules/procurement/decision_rules.py` and `decision_service.py`
hold the procurement business rules (VPL, suggested quantity, final
quantity). **This task did not modify either file.** Procurement is a
separate concern from sync transport and was left untouched.

## Critical rules

- Never modify `decision_rules.py` / `decision_service.py` without proven
  necessity and explicit sign-off.
- `sync.*` business tables are provisioned dynamically — don't hand-write
  DDL for them.
- Store Agent identity (`store_id`) comes from `agent_config.json`, never
  hardcoded in code.
- FILE_TRANSFER credentials (SFTP/SMTP/IMAP) are always `*_env` references
  to environment variables — never embedded in config files or code.
- FILE_TRANSFER is opt-in and additive: with it disabled (the default),
  DIRECT_HTTP behaves byte-for-byte as before this task.
