# Sync + Store Agent (Phase 2 & 3)

Phase 2 (Legacy Store Agent) and Phase 3 (Sync Foundation) are implemented. No
business modules are included.

## Where the code lives

- `core/agent/` — the Legacy Store Agent runtime:
  - `agent_manager.dart` — bootstrap/startup flow, health monitor, scheduler
    ownership, lifecycle.
  - `device_info_service.dart` — local device registration (UUID + platform/app
    metadata), cached in `device_information`.
  - `store_config_service.dart` — store configuration download + offline cache
    (with conflict-aware change detection).
  - `backend_health_service.dart` — `/health` probe, latency, API-version
    compatibility check.
  - `agent_settings*.dart` — persisted, user-tunable runtime settings.
  - `delta/` — concrete `EntityDeltaProcessor`s (`store_config`, `user_profile`).
- `core/sync/` — the offline sync engine:
  - `sync_manager.dart` — orchestrator; owns `SyncState`, drains the queue, runs
    deltas, reacts to connectivity, resumes after interruption.
  - `sync_queue.dart` / `sync_repository.dart` — durable operation queue
    (upload/download/retry/offline as views) + Drift persistence gateway.
  - `sync_scheduler.dart` — periodic background sync.
  - `connectivity_service.dart`, `retry_policy.dart`, `conflict_handler.dart`,
    `delta_processor.dart`, `sync_logger.dart`, `sync_status.dart`,
    `sync_state.dart`, `sync_events.dart`.
- `core/database/tables.dart` — sync-infrastructure Drift tables only
  (`device_information`, `sync_metadata`, `sync_configuration`, `sync_state`,
  `sync_queue`, `sync_history`). No business tables.
- UI: `features/sync/presentation/sync_status_screen.dart` and
  `features/agent/presentation/` (Device / Configuration / Agent Settings).
- `features/sync/data/` — read-only **network** sync overview: `GET
  /api/sync/control-center` (the same endpoint the HO web console's Sync
  Control Center uses), gated to platform users on the client since it isn't
  tenant-scoped server-side. Entirely separate from the device-local engine
  above — it doesn't touch the queue, Drift, or `core/sync` at all.

## Key decisions

- Device registration is **local-only**; the phone never writes to the desktop
  agent's `store_agent_registry`. Store config caches the plain store record, not
  the credential-bearing `/agent-config`. See `docs/API_CONTRACT.md`.
- The engine is transport-agnostic: what syncs is decided by the registered
  `EntityDeltaProcessor`s, so business entities can be added later without
  touching `core/sync`.

## Web build requirement: Drift WASM runtime assets

`core/database/connection/web.dart` opens the local database via
`WasmDatabase.open`, which needs two files served from the web root:
`web/sqlite3.wasm` (prebuilt sqlite3 binary) and `web/drift_worker.js`
(compiled from `web/drift_worker.dart`). Both are committed to the repo, so a
normal `flutter build web` / `flutter run -d chrome` picks them up
automatically — no extra step needed.

If `drift_worker.js` ever needs regenerating (e.g. after a `drift`/`sqlite3`
package upgrade), recompile it from the project root:
```
dart compile js web/drift_worker.dart -o web/drift_worker.js -O2
```
Without these two files, web builds still compile and the UI still renders,
but the local database fails to open — the Sync Status / Device Status /
Configuration Status screens show an `Error` state and nothing persists,
since (per this module's design) repositories are Drift-only and never fall
back to direct network reads.
