# Remote Order Agent

Integration between a **remote store's local OrderNMC** (SQL Server) and **Nexora
HO**, for stores that cannot be reached by HO's LAN direct-pull. The agent is
outbound-only: it pulls generated orders down, applies them into the store's
local `OrderManagement`, and pushes the store's order edits back up.

> Renamed from **NMVSyncAgent** when it was brought into this repo. The folder
> and the Nexora-side module are called `remote_order_agent`; the built Windows
> service / exe keep the internal `NMVSyncAgent` identifiers for now so the
> already-built-and-tested artifact is preserved (rebrand later if wanted).
> First (and currently only) deployment is store **NMV**.

## Pieces

| Path | What |
|---|---|
| `src/*.cs` | The .NET Framework 4.x C# Windows service (POS sync, order pull, result push, HMAC HO client, Settings window). Runs **on the store PC**. |
| `sql/` | Additive schema + trigger installed into the store's local `OrderNMC` (`nmv_change_queue`, `nmv_order_inbox`, trigger, etc.). Nothing existing is altered. |
| `install/` | PowerShell service install/uninstall + guarded VB build deploy/rollback. |
| `vb_changes/` | Modified `Form1.vb` + `SQL_Connection_Module.vb` for the legacy VB OrderManagement app (guards "Process Order"/Sync for managed stores; removes hard-coded `sa`). |
| `config/agent.json` | Store-PC config template (no secrets). |
| `docs/` | `01` design, `02` the HO API contract, `03` implementation report. **Read `02` to understand the wire protocol.** |
| `tests/` | Trigger tests, HO-stub end-to-end tests, VB guard tests (run on the store PC). |

## HO side (this repo, Python)

The agent's contract (`docs/02_HO_API_Contract.md`, base `/api/nmv/v1`, opaque
device token + HMAC-SHA256 signing) is implemented at
[`backend/modules/remote_order_agent/`](../backend/modules/remote_order_agent/):

| Route | Purpose |
|---|---|
| `POST /api/nmv/v1/agent/register` | Redeem a one-time enrollment code → `device_token` + `device_secret`. Unauthenticated (the code authorises it). |
| `POST /api/nmv/v1/agent/heartbeat` | Liveness + queue depth. |
| `GET  /api/nmv/v1/orders/pending` | The current HO order for the store (mapped to the agent's line shape + `lines_sha256`), until it has been ACKed. |
| `POST /api/nmv/v1/orders/{id}/ack` | Record APPLIED / REJECTED / DEFERRED. |
| `POST /api/nmv/v1/order-results` | Apply the store's order edits back into HO's `OrderManagement` (idempotent per `(store, queue_epoch, change_id)`). |

It **reuses** `modules.nmv_integration` for the actual OrderNMC data layer (order
reads, result apply, one-time enrollment codes) so order rows have a single
source of truth. Auth lives in the module's own HMAC dependency; the whole
`/api/nmv/v1` surface is allow-listed past the JWT `require_auth` middleware in
`api/app.py` (the device token is not a JWT).

**`device_secret`** is never stored: it is derived as
`HMAC_SHA256(server_jwt_secret, "nmv-agent-device-secret:" + device_id)` and
recomputed to verify each request — see `backend/modules/remote_order_agent/security.py`.

### HO-side order-details access for the store user

The HO Legacy-Order console was platform-admin-only. It is now relaxed so a
**non-admin user assigned to a store** (e.g. the `nmvpm` purchase manager) may
**GET that one store's read-only order views** (`/orders/{store}`, `qty-check`,
`suppliers`, `previous-orders`). Every mutating / ops / DB-recovery route stays
admin-only. See `require_order_console_access` in
`backend/modules/legacy_order/router.py`.

## End-to-end flow

```
POS (Shopaid, LAN) ─▶ agent ─▶ local OrderNMC          (stock/master/sales, offline)
HO /orders/pending ─▶ agent ─▶ local OrderManagement + OrderHeaderDetails
local VB edits ─▶ trigger ─▶ nmv_change_queue ─▶ agent ─▶ HO /order-results
```

## Deploying to a store PC (summary — see `docs/03` for detail)

1. Install the local DB objects: `sqlcmd ... -i sql/001_nmv_integration_install.sql -v DB=OrderNMC`.
2. Install the service (elevated): `install/install_service.ps1`.
3. Point it at Nexora HO: in *NMV Sync Agent Settings* (`NMVSyncAgent.exe --settings`)
   set `ho_base_url` to the Nexora HO URL; **keep `ho_api_prefix = api/nmv/v1`**.
4. Enroll: HO super admin generates a one-time code (**Sync → Device Management →
   "Generate a device enrollment code"**, store = NMV) → paste it in Settings →
   *Enroll device* → *Save & restart service*. The agent then registers against
   `/api/nmv/v1/agent/register` and begins syncing.
5. (Optional) Deploy the guarded VB build: `install/deploy_vb_build.ps1`.

## Verification status

- **HO contract (this repo):** implemented + covered by
  `backend/tests/test_remote_order_agent.py` (register → HMAC-signed pull,
  line-mapping + `lines_sha256`, ack lifecycle, result apply/dedup/reject, and
  the store-user order-view access matrix). All green, offline.
- **Agent + VB + SQL (store PC):** shipped as built & tested by the vendor
  package (`docs/03`, incl. a 44/44 HO-stub suite). **Not re-exercised here** —
  it needs the physical store PC, the real POS, and a .NET build, and must be
  run against this HO once a code is issued.
