# Nexora Application Audit, Startup Fix, and Development-Gap Report

Date: 2026-09-25  
Scope: `E:\Nexora`, with emphasis on the standalone Supplier Stock Electron client, HO API responsiveness, workspace disk usage, and Antigravity memory pressure.

## 1. Executive summary

Nexora is a multi-application retail/pharmacy platform. The principal runtime path is:

```text
Store SQL Server
  -> Store Agent (sync/heartbeat)
  -> HO FastAPI API + SQL Server
  -> React browser UI / standalone Electron client / Flutter mobile app
```

The Electron symptom—an error shortly after launch followed by records appearing later—had two concrete startup causes and one backend contributor:

1. The development launcher waited only for Vite. Its fixed five-second backend delay did not prove that the API could answer requests.
2. Safe GET requests failed immediately on brief gateway/network startup errors instead of retrying.
3. Store watchdog heartbeats repeatedly failed because `dbo.agent_watchdog_audit` had an idempotent migration file but no runtime migration hook. Each failure rolled back the heartbeat and emitted a large traceback, adding avoidable API/logging load.

The first two are fixed in the Electron client. Agent Ops schema provisioning is now wired into runtime and the missing database object was created and verified. The health endpoint was converted to a non-blocking async endpoint, but the running production-style API still has a significant long-tail latency problem under load. A service restart is required to activate the endpoint source change, and a controlled load test is required before calling the server-side issue closed.

Workspace cleanup removed 281.76 MB of generated Antigravity test profiles and Vite caches without deleting tracked source or business data. Antigravity was using 2,236.6 MB working set before the change and 2,279.3 MB before restart after the change; watcher exclusions only take effect after reopening the workspace, so no immediate RAM reduction is claimed.

## 2. Current application map

```text
Nexora/
├── backend/                         FastAPI HO API, SQL Server access, domain modules
│   ├── api/app.py                   API composition, middleware, startup hooks, health
│   ├── controllers/                 legacy/top-level HTTP controllers
│   ├── modules/                     domain modules and their SQL/repositories/services
│   ├── tests/                       backend-focused tests
│   └── .venv/                       generated local Python environment
├── frontend/                        main React 19 + TypeScript + Vite HO web UI
├── desktop/
│   └── supplier-stock-client/       standalone React + Vite + Electron application
│       ├── electron/                Electron main/preload processes
│       ├── scripts/                 development launch coordination
│       ├── src/                     renderer UI, API client, session state
│       ├── dist/                    generated renderer build
│       └── release/                 generated Electron installer output
├── store_agent/                     live per-store Windows sync agent
├── store_agent_setup/               store-agent installer/settings/watchdog tooling
├── ho_setup/                        HO installer and Windows-service tooling
├── mobile/                          Flutter mobile application
├── automation/                      repository automation CLI
├── deploy/                          deployment scripts/configuration samples
├── docs/                            architecture, business rules, ADRs, reports
├── tests/                           cross-cutting Store Agent/sync tests
├── .builddeps/ + .buildvenv/        generated packaging dependencies
├── .ms-playwright/                  generated browser binaries
├── dist/ + release/                 generated root build artifacts
└── scripts/                         repository-level operational scripts
```

Important: `frontend/` and `desktop/supplier-stock-client/` are separate React clients. `docs/Desktop_Platform_Architecture.md` describes an Electron wrapper around `frontend/`, while the actively inspected standalone client is a separate Electron application. That distinction is easy to miss and should be made explicit in the project index.

## 3. Changes made

### Electron startup and reliability

- `desktop/supplier-stock-client/scripts/wait-and-launch.mjs`
  - waits up to 60 seconds for both Vite and `http://127.0.0.1:8000/health`;
  - supports `NEXORA_API_HEALTH_URL` for a different development API;
  - prevents opening Electron against an API that is still starting.
- `desktop/supplier-stock-client/start-desktop-client.bat`
  - removes the unreliable fixed five-second delay;
  - delegates readiness to the health-aware launcher.
- `desktop/supplier-stock-client/src/api/client.js`
  - retries idempotent GET calls twice on 408, 425, 429, 502, 503, and 504;
  - retries network startup failures with 350 ms and 1,000 ms backoff;
  - never automatically retries POST/PUT/DELETE mutations;
  - preserves caller cancellation and existing per-request timeouts;
  - drains transient responses so Chromium can reuse connections.
- `desktop/supplier-stock-client/electron/main.cjs`
  - stops opening detached DevTools on every development launch;
  - opt in with `NEXORA_OPEN_DEVTOOLS=1`, while F12/Ctrl+Shift+I remains available.

### Backend load/error reduction

- `backend/modules/agent_ops/repository.py`
  - runs the existing idempotent `sql/0001_agent_ops.sql` once per process under a lock;
  - applies the guard to all Agent Ops repository entry points;
  - prevents the partially provisioned database state that caused every qualifying watchdog heartbeat to fail and roll back.
- `backend/api/app.py`
  - changes the no-I/O `/health` handler from a thread-pool function to an async handler so it need not wait for a free Starlette worker thread.
- The existing migration was applied once during this audit, and `OBJECT_ID('dbo.agent_watchdog_audit', 'U')` was verified present.

### Antigravity/workspace pressure

- `.vscode/settings.json`
  - excludes virtual environments, Node dependencies, generated builds, browser binaries, caches, logs, and Antigravity scratch profiles from file watching and search;
  - disables project-wide TypeScript diagnostic mode.
- `.gitignore`
  - keeps only the shared workspace settings trackable while other `.vscode` files remain ignored.
- `scripts/cleanup-workspace.ps1`
  - defaults to a dry run;
  - removes only an explicit allow-list of generated caches/test profiles with `-Execute`;
  - resolves every path and refuses any target outside the repository;
  - reports partial failures instead of claiming unsuccessful deletion.

## 4. Response-time evidence

These numbers are wall-clock samples from this machine, not a laboratory benchmark. The live API is concurrently serving store agents and sync traffic.

### Live `/health`, same 10-request curl method

| Measurement | Before | After schema repair/source fix | Interpretation |
|---|---:|---:|---|
| Successful responses | 8/10 | 9/10 | modest availability improvement in this sample |
| Median of successful responses | 264.8 ms | 5.3 ms | warm-path response improved substantially |
| P95 of successful responses | 2,484.5 ms | 4,992.6 ms | long-tail latency did not improve |
| Client-side timeouts | 2 at 10 s | 1 at 12 s | backend still stalls under load |

The median improvement is encouraging but cannot be attributed solely to the code change because load was not controlled. The timeout and worse tail prove the single running backend process remains a bottleneck. The async health change also requires the service process to restart before it is certainly active.

### Desktop transient-startup behavior

An automated client test used the sequence `503 -> 502 -> 200`:

| Behavior | Before | After |
|---|---|---|
| User-visible result | immediate error | records returned successfully |
| Recovery duration | not applicable (failed) | 1,393.5 ms |
| Requests | 1 | 3 safe GET attempts |
| Mutation retry | none | none |

This directly addresses the reported short-lived startup error. It does not mask persistent errors: a final failure is still shown after the bounded retries.

## 5. Storage and memory cleanup

### Removed safely

| Generated target | Reclaimed |
|---|---:|
| `.antigravity-repair` | 213.18 MB |
| `.antigravity-postrepair-test` | 28.35 MB |
| `.antigravity-clean-test` | 28.04 MB |
| `frontend/node_modules/.vite` | 6.84 MB |
| `desktop/supplier-stock-client/node_modules/.vite` | 5.36 MB |
| `.antigravity-empty-extensions` | negligible |
| **Total** | **281.76 MB** |

All removed targets were already ignored/generated and are rebuildable. No source, database, uploaded business data, environment, dependency installation, installer output, or Git object was removed.

The root `.pytest_cache` is inaccessible even with elevated removal and was left in place. Its measured size was effectively 0 MB. This is an ACL/ownership issue, not a meaningful storage consumer.

### Intentionally retained

- `backend/.venv`, `.buildvenv`, `.builddeps`: large but required for development/building.
- `node_modules`: large but required for local builds; only Vite’s rebuildable transform cache was removed.
- `.ms-playwright`: required browser runtime.
- `dist`, `release`, and desktop installer outputs: generated and large, but potentially required for deployment; not safe to assume unused.
- `docs/AI_ARCHIVE`: project documentation/history, not a disposable AI cache.
- untracked scripts/reports and the dirty working tree: treated as user development work.

### RAM finding

Antigravity used 17 processes and about 2.18–2.23 GB working set during the audit. Deleting disk caches does not free process RAM. The watcher exclusions require a full Antigravity workspace restart. After restart, compare the process-group working set after five idle minutes; that is the valid before/after measurement. If it remains above roughly 1.5 GB while idle, profile extensions and language servers next.

## 6. Development gaps, prioritized

### P0 — API availability under concurrent sync load

The single Uvicorn process on port 8000 intermittently fails to return even `/health` within 10–12 seconds. The UI fix prevents brief startup faults from leaking to users, but it cannot solve sustained server starvation.

Recommended next work:

1. Restart the backend in a maintenance window so the async health and runtime schema code are active.
2. Add request-duration logging with route, status, queue time, handler time, and a request ID.
3. Run a controlled 15-minute test that mixes store heartbeats/sync polling with desktop reads.
4. Identify event-loop blocking async routes and move blocking database/browser work to threads/processes.
5. Evaluate multiple API workers only after separating or proving singleton safety for WhatsApp warm-up and background services. The sync scheduler already has a database lock, but not every startup service is worker-safe.

Acceptance target: `/health` P95 below 250 ms and 100% success; initial desktop store/supplier lists P95 below 2 seconds on LAN.

### P0 — production verification of the Electron symptom

The renderer fix is built and tested, but a new Electron installer has not been packaged or installed during this audit. Package version `0.1.11`, test on a clean user profile, and record:

- process start to `ready-to-show`;
- first successful `/api/stores` response;
- first records painted;
- working set at 30 seconds and five minutes;
- offline and 503/504 recovery behavior.

### P1 — oversized renderer boundary

`desktop/supplier-stock-client/src/App.jsx` is 9,984 lines (about 471 KB). It mixes navigation, permissions, data loading, grids, label export, order workspace, settings, and screen-specific state. This increases reload cost, review risk, merge conflicts, and accidental cross-feature coupling.

Split by feature without changing behavior: `features/stock`, `features/supplier-analysis`, `features/labels`, `features/orders`, and `features/settings`, with shared hooks/components in `shared/`.

### P1 — bundle size and eager loading

The production build succeeds in 709 ms but reports large chunks:

- application JavaScript: 521.33 KB minified / 147.17 KB gzip;
- spreadsheet library chunk: 862.97 KB minified / 317.89 KB gzip.

Load export/spreadsheet code only when the user opens an export workflow, and lazy-load screen modules. This should improve first paint and reduce Electron renderer memory.

### P1 — migrations are inconsistent

Some modules self-provision, some depend on manually applied SQL, and Agent Ops had a migration that was not invoked. Establish one documented migration/bootstrap mechanism with a schema-version table and startup verification. Avoid silently swallowing schema failures for required modules.

### P1 — generated artifacts dominate repository scans

The workspace contains multi-gigabyte environments and releases next to source. Ignore rules help, but separating build output from the source root will reduce editor indexing, backup time, and accidental packaging.

### P2 — Electron hardening and observability

- `sandbox: false` remains enabled in the Electron renderer; assess preload compatibility and enable Chromium sandboxing.
- Add structured main/renderer startup logs and `did-fail-load`/`render-process-gone` handlers.
- Add an Electron smoke test that verifies API-unavailable, API-warming, authenticated restore, and record rendering states.
- GPU acceleration is globally disabled. Keep this only if a documented target-machine rendering defect requires it; otherwise benchmark CPU, RAM, and stability with default acceleration.

### P2 — project documentation drift

The desktop architecture document primarily describes the Electron wrapper in `frontend/`, while the reported application lives in `desktop/supplier-stock-client/`. Add a short decision record naming the supported desktop products and their intended convergence/deprecation path.

## 7. Proposed aligned tree (future move, not performed)

This layout separates deployable applications, shared packages, operational tooling, generated artifacts, and documentation:

```text
Nexora/
├── apps/
│   ├── ho-api/                       current backend/
│   ├── ho-web/                       current frontend/
│   ├── supplier-stock-desktop/       current desktop/supplier-stock-client/
│   └── mobile/                       current mobile/
├── services/
│   └── store-agent/                  current store_agent/
├── installers/
│   ├── ho/                           current ho_setup/
│   └── store-agent/                  current store_agent_setup/
├── packages/
│   ├── api-contracts/                generated/shared DTO contracts
│   ├── ui/                           reusable React UI where genuinely shared
│   └── business-rules/               documented/tested shared rules only
├── ops/
│   ├── automation/                   current automation/
│   ├── deploy/                       current deploy/
│   └── scripts/                      current scripts/
├── tests/
│   ├── integration/
│   └── end-to-end/
├── docs/
├── artifacts/                        ignored; builds/releases/installers
└── .cache/                           ignored; tool caches only
```

Do not perform this move as one large rename. First add stable commands at the root, then move one deployable unit at a time while preserving installer paths and Windows service configuration.

## 8. Validation completed

- Desktop production build: passed (`vite build`, 709 ms).
- API client tests: 2 passed.
  - transient GET recovery;
  - no automatic retry for POST.
- Agent Ops schema regression test: 1 passed.
- Python syntax compile: passed for `api/app.py` and `agent_ops/repository.py`.
- Node syntax checks: passed for Electron main and wait/launch script.
- Database verification: `dbo.agent_watchdog_audit` exists.
- Cleanup dry run and allow-listed execution completed; 281.76 MB reclaimed.

## 9. Completion status

Completed in source: Electron launch readiness, safe transient GET recovery, automatic Agent Ops schema provisioning, health-handler improvement, automatic DevTools memory reduction, shared watcher/search exclusions, safe cleanup tooling, cache cleanup, tests, and this report.

Still required operationally: restart/redeploy the HO API and Electron client, reopen Antigravity to activate watcher exclusions, then run the controlled production timing/memory acceptance test described above.

## 10. Unwanted spreadsheet, image, archive, and build-file inventory

This section is a read-only classification. Nothing listed below was deleted during this follow-up. “Remove” means the files are generated and can be recreated; apply the retention checks before deletion where noted.

### 10.1 Summary by file type

The scan excluded dependency trees (`node_modules`, Python virtual environments, `.builddeps`, `.git`, and Playwright browser binaries) so vendor assets do not distort the results.

| Type | Files | Size | Tracked/indexed | Untracked or ignored | Assessment |
|---|---:|---:|---:|---:|---|
| `.rar` | 1 | 207.01 MB | 1 staged | 0 | urgent review; database export archive |
| `.xls` | 360 | 47.96 MB | 0 | 360 | generated stock reports |
| `.xlsx` | 86 | 15.79 MB | 0 | 86 | generated reports/distribution files |
| `.png` | 330 | 27.64 MB | 43 | 287 | mostly WhatsApp diagnostics; tracked app assets should stay |
| `.bmp` | 88 | 1.99 MB | 0 | 88 | Electron/NSIS cache assets |
| `.7z` | 2 | 1.92 MB | 0 | 2 | Electron-builder NSIS cache |
| `.ico` | 78 | 1.08 MB | 1 | 77 | mostly Electron/NSIS cache assets |
| `.jpeg` / `.jpg` | 7 | 1.76 MB | 1 | 6 | sample/runtime invoices plus one required desktop logo |
| `.zip` | 2 | 1.72 MB | 1 | 1 | one source snapshot and one generated runtime bundle |
| `.pdf` | 1 | 0.28 MB | 0 | 1 | sample invoice |
| `.gif`, `.svg`, `.tmp`, `.bak`, `.csv` | 23 | about 0.24 MB | mixed | mixed | review individually; low space impact |

### 10.2 High-priority unwanted/generated groups

| Priority | Location | Files | Size | Details | Recommendation |
|---|---|---:|---:|---|---|
| Urgent | `backend/nexora_platform_export.rar` | 1 | 207.01 MB | Staged as a new Git file. Name indicates a database export and it may contain business/PII data. | Do not commit. Confirm backup location, unstage, securely remove or move outside the repository, and add archive dump patterns to `.gitignore`. |
| High | `backend/storage/whatsapp/debug/` | 507 | 208.52 MB | 169 HTML page captures (183.63 MB), 169 PNG screenshots (24.88 MB), and 169 JSON diagnostics. Dated 2026-08-14 through 2026-09-23. | Purge after retaining only captures tied to open incidents. Add age/count retention, for example 7 days or the newest 20 failures. These files can expose WhatsApp screen content. |
| High | `backend/storage/whatsapp/files/` | 326 | 37.83 MB | 264 `.xls` files (35.27 MB) and 62 `.xlsx` files (2.57 MB), mostly repeated outgoing stock reports. | Delete successfully sent attachments after a retention window. Keep only failed/pending sends referenced by the send log. |
| High | `backend/storage/distribution/` | 119 | 25.97 MB | 95 `.xls` reports (12.75 MB) and 24 `.xlsx` reports (13.22 MB). Dated 2026-08-14 through 2026-09-25. | Keep the latest report per store/type if operationally useful; archive or purge older generated copies. |
| High | `desktop/supplier-stock-client/.eb-cache/` | 710 total files | 18.67 MB | Electron-builder/NSIS downloads and extracted bitmap/icon/tool files. | Safe to remove; electron-builder downloads it again when packaging. |
| High | `desktop/supplier-stock-client/release/` | 1,259 | 722.51 MB | Seven installer EXEs plus `win-unpacked`. Latest is `0.1.11`; versions `0.1.6`–`0.1.10` remain. | After verifying `0.1.11`, retain the latest installer and remove older installers plus `win-unpacked`. Estimated reclaim: about 652.6 MB. |
| Review | root `dist/` | 81 | 198.63 MB | PyInstaller executables and unpacked `NexoraHOMailReceiver`. | Generated output. Remove only after confirming released copies exist elsewhere; fully rebuildable from specs/source. |
| Review | root `release/HO_Setup.exe` | 1 | 1,965.82 MB | HO installer built 2026-07-20. Largest single file in the workspace. | Move to release storage if it is still deployable; otherwise remove and rebuild when required. Do not delete before confirming deployment/backup status. |
| Review | `backend/modules/procurement.zip` | 1 | 0.44 MB | Tracked source-module snapshot already committed. Source also exists unpacked. | Review history/use; likely redundant archive, but remove through a normal Git change only after confirmation. |
| Review | `backend/scripts/_roundtrip_invoice.png` | 1 | 0.11 MB | Tracked generated/test image. | Keep only if it is an intentional regression fixture; otherwise remove through Git. |

The five high-priority generated/runtime groups, excluding root deployment artifacts and the database archive, represent roughly 943.6 MB of potential cleanup. The root `dist`, root `release`, and staged database archive add another 2.37 GB, but require explicit backup/deployment decisions first.

### 10.3 Excel report details

The repeated filenames identify generated operational exports rather than source templates:

| Pattern | Format | Count | Total | Date range |
|---|---|---:|---:|---|
| `NMW_Stock_NMV_YYYYMMDD` | `.xls` | 79 | 10.56 MB | 2026-08-14 to 2026-09-25 |
| `NMW_Stock_NMA_YYYYMMDD` | `.xls` | 70 | 9.37 MB | 2026-08-14 to 2026-09-25 |
| `NMW_Stock_NMC_YYYYMMDD` | `.xls` | 70 | 9.37 MB | 2026-08-14 to 2026-09-25 |
| `NMW_Stock_NMG_YYYYMMDD` | `.xls` | 70 | 9.37 MB | 2026-08-14 to 2026-09-25 |
| `NMW_Stock_NMS_YYYYMMDD` | `.xls` | 70 | 9.37 MB | 2026-08-14 to 2026-09-25 |
| `SupplierStock_NMA/NMC/NMG/NMS/NMV` | `.xlsx` | 5 | 12.30 MB | 2026-08-14 |
| Dated `NMW_Stock_*` | `.xlsx` | 55 | 2.58 MB | mainly 2026-08-14 |
| `NMW_SupplierStock_NMV_20260811_*` | `.xlsx` | 11 | 0.65 MB | 2026-08-14 |
| `daily_2026-08-09` and `daily_2026-08-12` | `.xlsx` | 12 | 0.10 MB | 2026-08-14 |
| `ExpiryStock_Nathan_Medicals_G_2026-08-30` | `.xlsx` | 1 | 0.07 MB | 2026-08-28 |

The WhatsApp folder often contains several byte-identical copies of the same daily report. Across the reviewed runtime/cache directories, SHA-256 grouping found 505 duplicate groups and 841 redundant copies, representing about 100.62 MB. That number includes HTML diagnostics and builder-cache binaries as well as spreadsheets, so it should not be added to the directory totals above.

### 10.4 Image details

Likely unwanted images:

- `backend/storage/whatsapp/debug/*.png`: 169 failure screenshots, 24.88 MB. These are diagnostic captures, not application assets.
- `desktop/supplier-stock-client/.eb-cache/**`: 88 BMP, 68 ICO, and 6 GIF files among the NSIS tool cache. They are downloaded/generated packaging dependencies.
- `data/document_extraction/10033/preview/page_1.jpg`: 0.37 MB generated preview. Retain only while document record `10033` needs it.
- `data/document_extraction/10033/original/*.jpeg`: 0.27 MB uploaded invoice. This is business data, not disposable cache; follow document-retention rules.
- `assects/sample invoice/`: four JPEG images and one PDF totaling 1.07 MB. These appear to be test/reference inputs. Confirm tests/documentation still use them before removing.

Required images to keep:

- desktop Axythic logos under `desktop/supplier-stock-client/src/assets/`;
- frontend logos/favicon/hero files under `frontend/src/assets/` and `frontend/public/`;
- Flutter Android, iOS, macOS, web, and Windows launcher icons;
- `installer/images/sync.png` unless the installer source no longer references it.

### 10.5 Small root-level investigation outputs

The following untracked files look like one-off diagnostics rather than application source. Together they use less than 80 KB, so cleanup value is organizational rather than storage-related:

- `cosec_punches.csv`
- `cosec_punches.json`
- `cosec_devices_report.txt`
- `cosec_api_and_punches_report.txt`
- `cosec_device_sync_report.txt`
- `cosec_matrix_hardware_sync_report.txt`
- `cosec_device_data_report.txt`
- `matrix_device_probe.txt`

The license inspection files at the root are already tracked. Treat them as documentation/security research until their purpose is reviewed; do not delete them as cache.

### 10.6 Safe cleanup order

1. Prevent the 207.01 MB database archive from entering Git and confirm its secure backup/disposal path.
2. Purge old WhatsApp debug captures after incident review.
3. Add retention-based cleanup for successfully sent WhatsApp attachments and generated distribution exports.
4. Verify installer `0.1.11`, then remove old desktop installers and `win-unpacked`.
5. Move valid HO/PyInstaller release binaries to release storage; clean root build outputs only after backup verification.
6. Leave all tracked application logos/icons and uploaded source documents untouched unless their owning feature is retired.
