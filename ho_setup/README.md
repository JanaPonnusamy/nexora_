# UniNex HO Setup

Builds **`HO_Setup.exe`** — a single Inno Setup installer that deploys the
UniNex Head Office (HO) backend + frontend to a fresh tenant PC. The interactive
deployment logic reuses the proven Store Agent patterns (PyInstaller-frozen
standalone executables; `sc.exe`-driven Windows service with auto-start and
restart-on-failure).

## Deliverables

| Artifact | What it is |
|----------|-----------|
| `release\HO_Setup.exe` | **the installer** (Inno Setup; bundles everything below) |
| `dist\HO_Backend\HO_Backend.exe` | standalone Windows-service host (embedded Python + FastAPI backend) |
| `dist\HO_Deploy.exe` | headless deploy helper / service installer (driven by the installer) |
| `dist\HO_Uninstall.exe` | standalone uninstaller |

`HO_Setup.exe` contains: `HO_Backend.exe`, the frontend build,
`NEXORA_PLATFORM.bak`, configuration templates, the service installer
(`HO_Deploy.exe`) and the uninstaller.

## Build (one command)

```bat
:: prerequisites: Python 3.12 x64, Node.js+npm, Inno Setup 6, ODBC Driver 17,
:: and ho_setup\assets\NEXORA_PLATFORM.bak
build.bat
:: -> release\HO_Setup.exe
package.bat       :: optional: zip + SHA-256
```

See [docs/HO_BUILD.md](../docs/HO_BUILD.md) for full build instructions and
[docs/HO_DEPLOYMENT.md](../docs/HO_DEPLOYMENT.md) for the operator runbook.

## Install (tenant PC, as Administrator)

Run `HO_Setup.exe`. The wizard collects the install folder, SQL Server settings
(with **Test Connection**) and the web address, then automatically:
generate config → restore + verify `NEXORA_PLATFORM.bak` → install + start the
`UniNexHO` Windows service → health check. HO is then live at
`http://<server>:<port>`.

## Package layout (`ho_setup\`)

| File | Role |
|------|------|
| `cli.py` → `HO_Deploy.exe` | test-sql / configure / restore / install-service / health / deploy / uninstall |
| `ho_service.py` | pywin32 service host running uvicorn (built into `HO_Backend.exe`) |
| `service_manager.py` | `sc.exe` service lifecycle (auto-start + restart-on-failure) |
| `sql_deployer.py` | test connection, restore `.bak` (auto file-remap), verify |
| `ho_config.py` | generates `ho.env`, `settings.json`, frontend `config.js` |
| `backend_deployer.py` / `frontend_deployer.py` | file deployment + SPA endpoint config |
| `health_check.py` | SQL → DB → service → API → frontend |
| `deployment.py` | rollback-protected orchestration (used by the standalone wizard) |
| `wizard.py` | optional standalone Tkinter wizard (dev / non-Inno use) |
| `uninstaller.py` → `HO_Uninstall.exe` | remove service + files (preserves DB unless `--dropdb`) |
| `*.spec` | PyInstaller build specs for the three exes |
| `build.py` / `package.py` | Python equivalents of `build.bat` / `package.bat` |
| `templates\ho.env.template`, `LICENSE.txt`, `assets\` | bundled installer assets |

The installer project itself is [installer/HO_Setup.iss](../installer/HO_Setup.iss).

## Service control (ops)

```bat
sc query UniNexHO
sc stop  UniNexHO
sc start UniNexHO
```

## Uninstall

Use **Apps & features**, the Start-menu *Uninstall UniNex HO*, or
`{app}\HO_Uninstall.exe`. The SQL database is preserved unless explicitly
dropped (`HO_Uninstall.exe /silent /dropdb`).
