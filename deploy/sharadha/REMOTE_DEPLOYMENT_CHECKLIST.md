# Sharadha — Remote Store Deployment Checklist

Three remote stores: **SMG**, **SMA**, **SMF**. Each store machine needs only the
agent installer and its store code — **no manual database editing** (SQL
credentials already live, encrypted, in HO from `seed_sharadha_stores.sql`).

HO endpoint (production): **https://ho.qvault.in**

---

## One-time HO preparation (do first, once)

- [ ] HO deployed and the service `UniNexHO` is **running**.
- [ ] HO reachable at **https://ho.qvault.in/health** → `{"status":"healthy"}`.
- [ ] `config\ho.env` matches [ho.env.production](ho.env.production) (public URLs + multi-origin CORS).
- [ ] Sharadha tenant exists in `dbo.tenants`.
- [ ] Ran [seed_sharadha_stores.sql](seed_sharadha_stores.sql) against `NEXORA_PLATFORM`
      → SMG, SMA, SMF present (verification SELECT shows all three).

---

## Per-store deployment (repeat for SMG, SMA, SMF)

On the **store machine**:

1. [ ] Copy **StoreAgent_Setup.exe** to the machine.
2. [ ] **Run as Administrator.**
3. [ ] In the wizard: HO URL defaults to **https://ho.qvault.in** → **Test Connection**.
4. [ ] Select tenant **Sharadha** → select this store (**SMG** / **SMA** / **SMF**).
   - *Or* import the generated config file
     [agents/agent_config.&lt;CODE&gt;.json](agents/) (tenant/store pre-filled).
5. [ ] Finish installation (files copied, service installed = Automatic, started).
6. [ ] **Automatic registration** with HO (agent calls `/agent/register`).
7. [ ] **Automatic heartbeat** (agent → `/agent/heartbeat`).
8. [ ] **Automatic first sync** (agent pulls config from
       `/api/stores/{store_id}/agent-config` and runs the first cycle).

### Optional: scripted prepare + verify (Administrator PowerShell)
```powershell
# Resolves identity from HO, writes config, installs+starts the service, verifies:
.\deploy_store_agent.ps1 -StoreCode SMA -AgentDist <path-to-built-NexoraStoreAgent>

# If the wizard already installed the agent, just (re)configure + verify:
.\deploy_store_agent.ps1 -StoreCode SMA -SkipInstall
```

### Per-store verification
- [ ] `sc query NexoraStoreAgent` → **RUNNING**.
- [ ] `D:\NexoraStoreAgent\logs\agent.log` shows `[AGENT] registered store <id>`.
- [ ] `agent.log` shows `[CATALOG] delta` and/or `[SYNC] cycle` (first sync).
- [ ] In HO, the store shows recent activity (Sync Administration → Store Health).

---

## Store reference (already seeded in HO — for confirmation only)

| Code | Store Name | SQL Server | Database | User | Branch |
|------|-----------|-----------|----------|------|--------|
| SMG  | WantedSMG | `SERVERT30\WONDERSOFT`     | shopaid  | sa | (none) |
| SMA  | WantedSMA | `DELL-DESKTOP\SQLEXPRESS`  | OrderNMC | sa | L |
| SMF  | WantedSMF | `DELL-DESKTOP\SQLEXPRESS`  | OrderNMC | sa | L |

> The store's SQL password is **not** entered on the store machine — the agent
> downloads it (encrypted) from HO and decrypts it locally with the shared
> Fernet key bundled in the agent.

---

## Rollback (per store)
- [ ] `sc stop NexoraStoreAgent && sc delete NexoraStoreAgent`
- [ ] Remove `D:\NexoraStoreAgent` (or run `NexoraStoreAgentSettings.exe` to reconfigure).
- HO data (the store row) is unaffected.
