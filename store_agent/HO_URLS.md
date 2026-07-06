# Store Agent — multiple HO routes (LAN + domain + static IP)

A store can now reach Head Office over **several routes at once** and the agent
uses whichever is reachable, failing over automatically. This fixes the outage
where a single `ho_url` was pointed at a domain/tunnel and every LAN store went
offline when that route was unreachable.

## Configure at install time (recommended)

The **Setup wizard** (`NexoraStoreAgentSetup.exe`) and the **Settings** utility now
take three routes — **LAN, Static IP, Domain** — and write them as `ho_urls` in
that order. Enter all three, click **Test Connection** (it uses the first
reachable one to load tenants/stores), pick the tenant + store, and install. Every
store then fails over LAN → static IP → domain automatically.

## Configure by hand (existing installs)

Edit each store's **`agent_config.json`** (in the agent install folder) and
replace the single `ho_url` with an ordered `ho_urls` list — **LAN first**, then
static IP, then domain — and restart the agent service:

```json
{
  "store_id": "…",
  "ho_urls": [
    "http://192.168.10.80:8000",   // local LAN (tried first)
    "https://ho.qvault.in",        // public domain / tunnel
    "http://203.0.113.10:8000"     // static IP
  ],
  "tenant_id": "…"
}
```

Then restart the store agent service.

**Back-compat:** the old single `"ho_url": "…"` still works, and it may be a
comma-separated list (`"ho_url": "http://192.168.10.80:8000, https://ho.qvault.in"`).
The env var `NEXORA_HO_URLS` (comma separated) overrides the file for a quick ops
fix without editing configs.

## Behaviour

- On start / config load the agent probes each route's `/health` and uses the
  first that answers; single-URL configs are used directly (no probe).
- The **heartbeat** (what marks a store ONLINE) and the **sync loop** both target
  the active route; on a network failure the agent rotates to the next route on
  the following cycle — no restart needed.
- If **no** route answers, it keeps retrying (with backoff) instead of crashing,
  so a store auto-recovers the moment any route comes back.

## HO server side (browser SPA over multiple hosts)

The API accepts the SPA from multiple origins too:

- When the HO service also serves the SPA (`UNINEX_FRONTEND_DIR` set), leave
  `UNINEX_API_URL` **empty** — the SPA calls whichever host loaded it, so LAN IP,
  domain and static IP all work from one deployment (same-origin, no CORS needed).
- If the SPA is hosted separately, list every origin in `UNINEX_CORS_ORIGINS`
  (comma separated) or match a subnet with `UNINEX_CORS_ORIGIN_REGEX`
  (see `backend/.env.example`).
