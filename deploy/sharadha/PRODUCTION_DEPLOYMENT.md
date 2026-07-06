# Sharadha — Production Deployment (qvault.in)

First real production deployment of UniNex for the **Sharadha** tenant, with the
HO published on the Internet at **https://ho.qvault.in** and three remote Store
Agents (SMG, SMA, SMF). Reuses the existing HO installer, Store Agent and Sync
modules — no architectural changes.

All artifacts live in `deploy/sharadha/`:

| File | Purpose | Spec section |
|------|---------|--------------|
| [ho.env.production](ho.env.production) | HO production configuration (URLs, multi-origin CORS) | 1 |
| [seed_sharadha_stores.sql](seed_sharadha_stores.sql) | Idempotent tenant store seed | 2 |
| [agents/agent_config.*.json](agents/) | Per-store agent config templates | 3 |
| [agents/sharadha_stores.csv](agents/sharadha_stores.csv) | Ops reference of seeded stores | 3 |
| [deploy_store_agent.ps1](deploy_store_agent.ps1) | Agent install + register + verify script | 3 |
| [REMOTE_DEPLOYMENT_CHECKLIST.md](REMOTE_DEPLOYMENT_CHECKLIST.md) | Per-store checklist | 4 |

---

## 1. HO configuration for Internet access

Public domain **qvault.in** → HO at **https://ho.qvault.in**.

### 1.1 Configuration values (`config\ho.env`)
Deploy [ho.env.production](ho.env.production) as `C:\Program Files\UniNex\HO\config\ho.env`:

```
UNINEX_API_URL=https://ho.qvault.in
UNINEX_FRONTEND_URL=https://ho.qvault.in
UNINEX_CORS_ORIGINS=http://localhost:8000,http://DELL-DESKTOP:8000,http://192.168.1.9:8000,https://ho.qvault.in
```

`UNINEX_CORS_ORIGINS` is **comma-separated, multiple origins** — `backend/api/app.py`
already splits it into a list (`_allowed_origins`), so no single origin is hardcoded.
The SPA is served same-origin from `https://ho.qvault.in` (so CORS isn't even
exercised in normal use); the extra origins cover localhost, the LAN hostname
`DELL-DESKTOP` and IP `192.168.1.9` during rollout.

Apply: `sc stop UniNexHO & sc start UniNexHO`.

### 1.2 Store Agent default HO URL
Updated to `https://ho.qvault.in` in:
- the Store Agent setup wizard default field (`store_agent_setup/wizard.py`),
- the deployment script default (`deploy_store_agent.ps1 -HoUrl`),
- the agent config templates (`agents/agent_config.*.json`).

The runtime fallback in `store_agent/config.py` is only used when **no**
`agent_config.json` is deployed (dev/test); production always ships a config, so
it is intentionally left unchanged to avoid disturbing local tests.

### 1.3 TLS / reverse proxy (Internet exposure)
The HO service listens on `UNINEX_HOST:UNINEX_PORT` (0.0.0.0:8000). Terminate TLS
for `ho.qvault.in` at a reverse proxy on the HO box and forward to the service:

- **IIS (ARR/URL-Rewrite)** or **nginx**: `https://ho.qvault.in` → `http://127.0.0.1:8000`.
- DNS: `ho.qvault.in` A-record → HO public IP.
- Firewall: allow inbound 443; keep 8000 private to the proxy.
- Certificate: issue for `ho.qvault.in` (e.g. Let's Encrypt / commercial).

> No backend code change is needed for HTTPS — TLS is handled by the proxy and
> `UNINEX_API_URL`/`UNINEX_FRONTEND_URL` already advertise the HTTPS domain to
> the SPA (via the generated `/config.js`).

---

## 2. Tenant seed (SMG, SMA, SMF)

Run [seed_sharadha_stores.sql](seed_sharadha_stores.sql) against the HO database:

```bat
sqlcmd -S <HO_SQL_INSTANCE> -d NEXORA_PLATFORM -E -b -i seed_sharadha_stores.sql
```

Properties:
- **Tenant auto-resolved** (`tenant_code` / `tenant_abbreviation` / `tenant_name` =
  `Sharadha`); aborts with a clear error if the tenant is missing. No hardcoded
  `tenant_id`.
- **Idempotent**: each store inserted only if `(tenant_id, store_code)` is absent.
- `store_id` via `NEWID()`.
- `password_encrypted` is a **Fernet token for `Admin123`** produced by the
  existing `StoreCryptoService.encrypt_password` routine and decryptable by the
  agent's `StoreAgentConfigDecryptionService` with the shared key
  `store_agent/config/fernet.key`. (Regeneration command is in the script header.)
- `created_at` / `updated_at` = `GETDATE()`; runtime fields (`last_sync_time`,
  `last_sync_status`, `last_seen`, `connection_status`, `heartbeat_ip`) left NULL.

> **Key consistency:** the HO and all agents must share the same `fernet.key`.
> The agent installer bundles `store_agent/config/fernet.key`, and the seed's
> tokens were generated with that same key, so decryption succeeds out of the box.
> If the key is ever rotated, regenerate the seed literals (see script header)
> and rebuild the agents.

---

## 3. Store Agent configuration & deployment script

SQL credentials live in HO (step 2), so the agent needs only its **identity +
HO URL**. [deploy_store_agent.ps1](deploy_store_agent.ps1) automates a store:

1. Tests HO (`/health`).
2. Resolves `tenant_id` + `store_id` from HO by `store_code`
   (`/api/tenants`, `/api/stores/tenant/{id}`) — no DB editing.
3. Writes `agent_config.json` (ho_url, tenant, store identity, log level).
4. Installs the Windows service (`sc create … start= auto`, restart-on-failure).
5. Starts the service.
6. Verifies registration + heartbeat (`agent.log`: `[AGENT] registered`).
7. Verifies the first sync (`agent.log`: `[SYNC] cycle` / `[CATALOG] delta`).

```powershell
# fully scripted (copies built agent dist, installs, verifies)
.\deploy_store_agent.ps1 -StoreCode SMG -AgentDist D:\dist\NexoraStoreAgent
.\deploy_store_agent.ps1 -StoreCode SMA -AgentDist D:\dist\NexoraStoreAgent
.\deploy_store_agent.ps1 -StoreCode SMF -AgentDist D:\dist\NexoraStoreAgent
```

The HO URL comes from `-HoUrl` and **defaults to `https://ho.qvault.in`**.

---

## 4. Remote deployment (three stores)

Per store, the operator only needs to: copy `StoreAgent_Setup.exe`, run as
Administrator, pick tenant/store (or import the generated config), finish — then
registration, heartbeat and first sync happen automatically. Full steps and
verification are in [REMOTE_DEPLOYMENT_CHECKLIST.md](REMOTE_DEPLOYMENT_CHECKLIST.md).

```
Copy StoreAgent_Setup.exe ─► Run as Admin ─► (HO URL = https://ho.qvault.in, Test)
   ─► Select Sharadha + store / import agent_config.<CODE>.json
   ─► Finish ─► auto register ─► auto heartbeat ─► auto first sync ─► Production
```

> `StoreAgent_Setup.exe` is the existing wizard, built as `NexoraStoreAgentSetup.exe`
> by `python -m store_agent_setup.build` (rename on distribution if desired).

---

## 5. End-to-end order of operations

1. Publish DNS + TLS for `ho.qvault.in` → HO box (reverse proxy → :8000).
2. Deploy HO with `ho.env.production`; confirm `https://ho.qvault.in/health`.
3. Ensure the **Sharadha** tenant exists; run `seed_sharadha_stores.sql`.
4. Deploy each Store Agent (SMG, SMA, SMF) per the checklist.
5. Confirm in HO → Sync Administration → Store Health that all three stores are
   online and have completed a first sync.

## Reused components (unchanged)
- HO installer / service: `ho_setup/`, `HO_Setup.exe`, service `UniNexHO`.
- Store Agent runtime + service: `store_agent/`, `store_agent_setup/`, service
  `NexoraStoreAgent`.
- HO API: `/health`, `/api/tenants`, `/api/stores/tenant/{id}`,
  `/api/stores/{store_id}/agent-config`, `/agent/register`, `/agent/heartbeat`.
- Crypto: `StoreCryptoService` (Fernet) + shared `fernet.key`.
- Sync module: unchanged; agents drive it via the existing runtime.
