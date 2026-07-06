# Nexora Store Agent Setup Wizard

One packaged application that deploys the Store Agent to **any** store. No
`STORE_ID`, `TENANT_ID`, or `HO_URL` is hardcoded — all chosen at install time
and downloaded from HO.

## Wizard flow
1. Welcome
2. Enter HO URL + **Test Connection** (`GET /health`)
3. Load tenants (`GET /api/tenants`) and select one
4. Load stores (`GET /api/stores?tenant_id=…`) and select one
5. Installation location (defaults to `D:\NexoraStoreAgent`, else `C:\NexoraStoreAgent`)
6. Download configuration (`GET /api/stores/{store_id}/agent-config`)
7. Install files (creates `logs cache runtime updates backups`)
8. Register Windows service `NexoraStoreAgent` (startup = Automatic)
9. Start service
10. Validate: HO reachable, config downloaded, service installed, service
    running, heartbeat successful → **Installation Successful**

## Run from source (development)
```
pip install -r store_agent_setup/requirements.txt
python -m store_agent_setup.wizard            # launch the wizard GUI
python -m store_agent_setup.settings_app      # post-install settings utility
```

## Build / package (PyInstaller)
```
python -m store_agent_setup.build             # builds all three exes into dist\
```
Produces in `dist\`:
- `NexoraStoreAgent.exe` — Windows service host (bundles the agent runtime)
- `NexoraStoreAgentSettings.exe` — change HO URL / store / log level later
- `NexoraStoreAgentSetup.exe` — **the wizard** (bundles the two above)

## Run the installer
```
dist\NexoraStoreAgentSetup.exe                # run as Administrator
```

## Manual service control (from source / for ops)
```
python -m store_agent_setup.agent_service --startup auto install
python -m store_agent_setup.agent_service start
python -m store_agent_setup.agent_service stop
python -m store_agent_setup.agent_service remove
```

## Validation
```
sc query NexoraStoreAgent                     # state = RUNNING
type D:\NexoraStoreAgent\agent_config.json    # store identity
python -m pytest tests/test_store_agent_setup.py -v
```

## Post-install reconfiguration
Run `NexoraStoreAgentSettings.exe` (or `python -m store_agent_setup.settings_app`).
Apply = Stop Service → Update Config → Validate → Restart Service.
```
