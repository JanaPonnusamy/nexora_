# NEXORA PROJECT INDEX

Navigation map. Generated from repository inspection; see `PROJECT.md` /
`PROJECT_DETAIL.md` for narrative context.

## 1. Applications

| App | Location | Entry point |
|---|---|---|
| HO Backend | `backend/` | `backend/api/app.py` |
| HO Frontend | `frontend/` | `frontend/src/App.tsx` |
| Store Agent | `store_agent/` | `store_agent/run_agent.py` (production); `main.py`/`runtime/*` are unused earlier scaffolding |
| Store Agent Setup | `store_agent_setup/` | `wizard.py`, `settings_app.py`, `watchdog_service.py` |
| **Store Mail Transfer (new, opt-in)** | `store_agent/` | `mail_transfer_main.py` -> `NexoraMailTransfer.exe`; hosted by `store_agent_setup/mail_transfer_service.py` |
| Desktop Supplier-Stock Client | `desktop/supplier-stock-client/` | `src/main.jsx`, `electron/main.cjs` |
| Mobile | `mobile/` | `mobile/lib/` (Flutter) |
| HO Setup | `ho_setup/` | `ho_setup/cli.py` |
| **HO Mail Receiver (new, opt-in)** | `backend/` | `mail_receiver_main.py` -> `NexoraHOMailReceiver.exe`; hosted by `ho_setup/mail_receiver_service.py` |
| Automation CLI | `automation/` | `automation/__main__.py` |

## 2. HO Menu / 3. HO Screens (frontend route groups)

| Route group | Capability | Pages dir |
|---|---|---|
| `/overview`, `/platform/*` | PLATFORM | `pages/platform/` |
| `/administration/*` | ADMINISTRATION | `pages/administration/` |
| `/sync/live\|schedules\|config\|mapping\|agents\|mail-transfer` | SYNC | `pages/sync/` |
| `/procurement/*` (console, cycles, refreshes, workspace, intelligence, compare, shelf-sort, distribution) | PROCUREMENT | `pages/procurement/` |
| `/product-mapping` | — | `pages/mapping/` |
| `/stock-availability`, `/stock-check-report`, `/stock-integrity` | — | `pages/stock*` |
| `/label-exporter(+box-workspace)` | — | `pages/label-export/` |
| `/nmw-sales-report` | — | `pages/nmw-sales/` |
| `/document-extraction/review\|history` | — | `pages/document-extraction/` |
| `/reports`, `/expiry-report`, `/expiry-stock`, `/non-moving-report`, `/sale-analysis` | — | top-level + module dirs |
| `/time-report`, `/pass-gen`, `/legacy-order(+workspace)`, `/whatsapp`, `/settings` | — | respective dirs |

Router: `frontend/src/routes/AppRouter.tsx`. Layout: `frontend/src/layouts/AppShell.tsx`.

## 4. Store Menu / 5. Store Screens

Store-facing UI lives in the Electron desktop clients
(`desktop/supplier-stock-client/`), not in the HO frontend. The Store Agent
itself (`store_agent/`) is headless (no UI) except the Settings app
(`store_agent_setup/settings_app.py`).

## 6. Store Agent

| Concern | Files |
|---|---|
| Identity/config | `config.py`, `agent_config.json` |
| SQL connection | `sql_connection_factory.py`, `runtime_sql_connection_service.py` |
| Schema discovery/catalog | `schema_scanner.py`, `catalog/*` |
| DIRECT_HTTP sync engine | `services/sync_runtime_orchestrator.py`, `services/data_extraction_service.py`, `services/hash_generation_service.py`, `services/chunk_builder_service.py`, `services/sqlite_cache_service.py` |
| DIRECT_HTTP transport | `services/task_polling_service.py`, `services/catalog_sync_service.py`, `services/sync_sender_service.py`, `services/sync_ack_processor.py` |
| **FILE_TRANSFER (new)** | `file_transfer/__init__.py`, `transport_base.py`, `file_drop_transport.py`, `sftp_transport.py`, `email_transport.py`, `transport_factory.py`, `package_builder.py`, `outbox.py`, `config.py`, `sync_dispatcher.py` (now also exposes `run_delivery_only()`); orchestrator: `services/file_transfer_runtime_orchestrator.py` |
| Entrypoint | `run_agent.py` (for EMAIL transport, builds packages only -- delivery is `mail_transfer_main.py`'s job) |
| **Mail Transfer entrypoint (new, EMAIL-only)** | `mail_transfer_main.py` |

## 7. Backend Modules

| Module | Purpose |
|---|---|
| `agent_ops` | Remote control + self-update for store agents |
| `audit` | Append-only audit trail (admin, read-only) |
| `document_extraction` | Invoice/document OCR extraction pipeline |
| `expiry_report`, `expiry_stock`, `nonmoving_report`, `sale_analysis`, `stock_availability`, `stock_check_report`, `stock_integrity`, `reports` | Read-only reports over `sync.*` |
| `grid_settings` | Per-user grid display settings |
| `label_exporter` | Label generation/printing + review workflow |
| `legacy_order` | Legacy Order console (order workflow, supplier stock rack) |
| `mobile_bff` | Mobile app backend-for-frontend (`/api/mobile/v1`) |
| `nmw_sales_report` | NMW warehouse->store dispatch bill reporting |
| `pass_gen` | Legacy store passcode generator |
| `procurement` | Core procurement engine (cycles, VPL, product intelligence, distribution) — **not modified by this task** |
| `product_mapping` | Cross-store product matching engine |
| `schema_sync` | Dev->prod DB schema diff/apply tool |
| `store_agent` | Backend-side store agent config API (`/api/store-agent`) |
| `supplier_stock_analysis` | Admin-tier supplier stock analysis |
| `sync` | HO<->Store synchronization (see §12) |
| `time_report` | COSEC attendance reporting |
| `whatsapp` | WhatsApp integration |

## 8. API Routes (sync-relevant; unattended-agent surface is unauthenticated by design)

| API | Method | Router | Purpose |
|---|---|---|---|
| `/api/sync/tasks/create` | POST | `runtime_router` | Manual "Sync Now" (DIRECT_HTTP) |
| `/api/sync/tasks/pending/{store_id}` | GET | `runtime_router` | Agent poll |
| `/api/sync/tasks/{id}/start\|complete\|fail` | POST | `runtime_router` | Task lifecycle |
| `/api/sync/configuration/{task_id}` | GET | `runtime_router` | Table/column config download |
| `/api/sync/chunks/upload` | POST | `runtime_router` | Chunk upload -> stage+MERGE |
| `/api/sync/chunks/ack` | POST | `runtime_router` | Chunk ack |
| `/api/sync/chunks/status/{execution_id}` | GET | `runtime_router` | Chunk status |
| `/api/sync/live`, `/api/sync/control`, `/api/sync/table-stats` | GET/POST | `runtime_router` | Live Operations UI |
| `/agent/register`, `/agent/heartbeat`, `/agent/tasks/poll` | POST/GET | `runtime_router` (agent sub-router) | Heartbeat/liveness |
| `/api/sync/schema/register` | POST | `router.py` | Schema registration |
| `/api/sync/catalog/{tables\|columns\|full}` | GET | `catalog_router` | Store schema catalog |
| `/api/sync/table-registry/populate` | POST | `table_registry_router` | One-time promotion |
| **`/api/sync/file-transfer/status`** | GET | `file_transfer_admin_controller` | FILE_TRANSFER receiver status (new) |
| **`/api/sync/file-transfer/packages`** | GET | `file_transfer_admin_controller` | Package audit list (new) |
| **`/api/sync/file-transfer/mail-config`** | GET | `file_transfer_admin_controller` | Mail config view (env-derived, no password) (new, Phase 2) |
| **`/api/sync/file-transfer/mail-config/test-smtp`** | POST | `file_transfer_admin_controller` | Real SMTP connection test (new, Phase 2) |
| **`/api/sync/file-transfer/mail-config/test-imap`** | POST | `file_transfer_admin_controller` | Real IMAP connection test (new, Phase 2) |

## 9. Database Schemas

`dbo` (platform/legacy), `procurement` (procurement's own tables), `sync`
(store-data mirror + sync metadata, including the new
`sync.file_sync_packages`).

## 10. Important Tables

| Table | Schema | Purpose |
|---|---|---|
| `sync_table_master`, `sync_column_mapping` | sync | What/how to sync |
| `sync_execution`, `sync_chunk_execution`, `sync_execution_details`, `sync_execution_audit` | dbo | Run/chunk ledger (shared by DIRECT_HTTP and FILE_TRANSFER) |
| `sync_table_progress` | sync | Live progress metrics |
| `sync_schedule` | dbo | Per-tenant sync interval |
| **`file_sync_packages`** | sync | **New**: FILE_TRANSFER package idempotency/audit ledger |
| `stores`, `store_agent_registry` | dbo | Store identity, agent heartbeat state |

## 11. SQL Migrations

Convention: `backend/modules/<module>/sql/NNNN_description.sql`, applied
idempotently via each module's `ensure_schema()` (self-provisioning on
first repository call — no external migration runner). New for this task:
`backend/modules/sync/sql/0001_file_sync_packages.sql`.

## 12. Sync Components

DIRECT_HTTP: `backend/modules/sync/runtime_*`, `scheduler_*`,
`schema_evolution.py`. FILE_TRANSFER (new):
`backend/modules/sync/file_transfer_repository.py`,
`file_transfer_validator.py`, `file_transfer_receiver_service.py`,
`file_transfer_scheduler.py` (now also exposes `run_forever()`, and
self-gates its in-process thread off for EMAIL mode), `file_transfer_config.py`,
`file_transfer_transport/` (`base.py`, `file_drop.py`, `sftp.py`,
`email.py`, `factory.py`); agent side: `store_agent/file_transfer/*`,
`store_agent/services/file_transfer_runtime_orchestrator.py`. Phase 2
standalone mail hosts (EMAIL-only, opt-in): `backend/mail_receiver_main.py`
+ `ho_setup/mail_receiver_service.py` (HO), `store_agent/mail_transfer_main.py`
+ `store_agent_setup/mail_transfer_service.py` (store).

## 13. Procurement Components

`backend/modules/procurement/` — `decision_rules.py`, `decision_service.py`
(untouched), `orchestration_service.py`, `pm_router.py`,
`workspace_service.py`, `network_movement_*` (uncommitted prior work, not
part of this task).

## 14. Reports

`backend/modules/reports/`, plus dedicated report modules:
`expiry_report`, `expiry_stock`, `nonmoving_report`, `sale_analysis`,
`nmw_sales_report`, `time_report`, `stock_check_report`, `stock_integrity`.

## 15. Authentication

JWT-based for the HO frontend/admin surface (`dependencies/auth.py`,
`get_current_user`). The store-agent-facing sync protocol is unauthenticated
by design (see `PROJECT_DETAIL.md` §35) — pre-existing, not changed here.
The new `/api/sync/file-transfer/*` admin endpoints use the same
`get_current_user` gate as every other admin controller.

## 16. Configuration

Store Agent: `agent_config.json` (`store_id`, `ho_urls`, and now
`file_transfer.{enabled,interval_seconds,mail_transfer_interval_seconds,transport}`),
env var overrides (`NEXORA_HO_URLS`, `NEXORA_FILE_TRANSFER_INTERVAL_SECONDS`,
`NEXORA_MAIL_TRANSFER_INTERVAL_SECONDS`, `NEXORA_INSTALL_PATH`). HO:
environment variables (`NEXORA_SYNC_MAX_CONCURRENT`, `NEXORA_SYNC_TICK_SECONDS`,
and now `NEXORA_FILE_TRANSFER_ENABLED`, `NEXORA_FILE_TRANSFER_TICK_SECONDS`,
`NEXORA_FILE_TRANSFER_MODE`, plus per-transport `NEXORA_FILE_TRANSFER_*`
vars — see `backend/modules/sync/file_transfer_config.py` docstring). Both
the Store Mail Transfer service and the HO Mail Receiver service read the
SAME config sources (`agent_config.json` / env vars respectively) as the
main agent/backend process -- no separate config store was introduced.

## 17. Tests

`tests/` (root, ~95 files, store-agent/sync/procurement, pure-Python where
possible). `backend/tests/` (~15 files). New for this task:
`tests/test_file_transfer_package_builder.py`,
`tests/test_file_transfer_transports.py`,
`tests/test_file_transfer_outbox.py`,
`backend/tests/test_file_transfer_validator.py`,
`backend/tests/test_file_transfer_receiver_transport.py`. New for the
email-retry fix: `tests/test_file_transfer_email_transport.py`,
`backend/tests/test_file_transfer_email_transport.py` (mocked
imaplib/smtplib, no real mailbox). New for Phase 2 extraction:
`tests/test_file_transfer_sync_dispatcher_delivery_only.py`,
`tests/test_run_agent_email_delegation.py`,
`backend/tests/test_file_transfer_scheduler_email_gating.py`,
`backend/tests/test_file_transfer_mail_config_endpoints.py`.

## 18. Build / Deployment

`launch.bat` (dev), `build.bat` -> `release/HO_Setup.exe`, `package.bat`,
`redeploy.bat`. Store Agent PyInstaller specs at repo root
(`NexoraStoreAgent*.spec`). `ho_setup/`, `store_agent_setup/` installer
builders. `deploy/sharadha/` a specific tenant's deployment playbook.
Phase 2 (opt-in, EMAIL-only): `python -m store_agent_setup.build
mail_transfer` -> `dist/NexoraMailTransfer.exe`; `python -m ho_setup.build
mail_receiver` (spec: `ho_setup/HO_MailReceiver.spec`) ->
`dist/NexoraHOMailReceiver/NexoraHOMailReceiver.exe`. Neither is built by
the default wizard flow.

## 19. Important Files

`store_agent/run_agent.py` (production entrypoint),
`store_agent/config.py` (multi-URL failover),
`backend/modules/sync/runtime_repository.py` (the MERGE engine every sync
path ultimately uses), `backend/api/app.py` (router/startup registration).

## 20. Known Issues

See `PROJECT_DETAIL.md` §29 (dead scaffolding code, 3 pre-existing failing
tests unrelated to this task). The email-transport retry limitation
previously noted here (§33) has been fixed -- see §33 for the corrected
`\Seen`-on-terminal-outcome-only contract and the new
`max_attachment_bytes` guard.

## 21. Architecture Decisions

FILE_TRANSFER reuses the DIRECT_HTTP extraction/hash/chunk engine and the
HO-side staging/MERGE engine verbatim; only package assembly and transport
are new. See `PROJECT_DETAIL.md` §31 and the final implementation report's
"Architecture Decision" section for the full rationale.
