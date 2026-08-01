# Sync (Phase 2)

Reserved for the Legacy Store Agent + Sync module. Not implemented in Phase 1.

Planned responsibilities:
- Offline-first cache of `sync.*` data via Drift (`core/database`).
- Delta pull/refresh against the backend sync endpoints.
- Connectivity/failover handling (HO multi-URL: LAN / domain / static IP).
