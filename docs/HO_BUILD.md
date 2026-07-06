# Building HO_Setup.exe

This guide produces the distributable **`release\HO_Setup.exe`** — a single Inno
Setup installer that bundles everything needed to deploy the UniNex Head Office.
Run it on a **developer/build machine**, not the tenant.

## Pipeline

```
build.bat
   |
   |-- npm run build            (frontend\dist)
   |-- PyInstaller HO_Backend.spec    -> dist\HO_Backend\HO_Backend.exe
   |-- PyInstaller HO_Deploy.spec     -> dist\HO_Deploy.exe
   |-- PyInstaller HO_Uninstall.spec  -> dist\HO_Uninstall.exe
   |-- ISCC installer\HO_Setup.iss
   v
release\HO_Setup.exe          (single, production-ready installer)
```

## 1. Build prerequisites

| Requirement | Notes |
|-------------|-------|
| Windows 10/11 or Windows Server | PyInstaller + Inno produce native Windows artifacts |
| Python 3.12 (64-bit) on PATH | matches the project's bytecode (cpython-312) |
| Node.js 18+ + npm | builds the frontend |
| **Inno Setup 6** (`ISCC.exe`) | https://jrsoftware.org/isdl.php |
| ODBC Driver 17 for SQL Server | required by `pyodbc` |
| SQL Server (any, reachable) | only to *produce* `NEXORA_PLATFORM.bak` |

## 2. Provide the database backup

The installer provisions the database by **restoring a bundled backup** instead
of running schema scripts. Produce a clean, fully-seeded backup of
`NEXORA_PLATFORM` (schema, stored procedures, seed roles/permissions, initial
platform admin) and place it at:

```
ho_setup\assets\NEXORA_PLATFORM.bak
```

See [ho_setup/assets/README.md](../ho_setup/assets/README.md) for the exact
`BACKUP DATABASE` command. The `.bak` is git-ignored; keep it in your artifact
store.

## 3. Build (one command)

From the repository root:

```bat
build.bat
```

`build.bat` checks the backup, builds the frontend (if `frontend\dist` is
absent), installs Python deps, runs PyInstaller on the three spec files,
`selftest`s the backend bundle, locates `ISCC.exe`, and compiles the installer.
Result: **`release\HO_Setup.exe`**.

## 4. Package for distribution (optional)

```bat
package.bat
```

Writes `release\SHA256SUMS.txt` and `release\UniNex_HO_Installer.zip`.

## What HO_Setup.exe contains

| Bundled item | Source | Installed to |
|--------------|--------|--------------|
| `HO_Backend.exe` + `_internal\` | `dist\HO_Backend\` | `{app}` |
| Frontend build | `frontend\dist\` | `{app}\frontend` |
| `NEXORA_PLATFORM.bak` | `ho_setup\assets\` | `{app}\backups` |
| `HO_Deploy.exe` (service installer / deploy helper) | `dist\` | `{app}` (+ temp during wizard) |
| `HO_Uninstall.exe` (standalone uninstaller) | `dist\` | `{app}` |
| `ho.env.template`, `LICENSE.txt` | `ho_setup\` | `{app}\config`, `{app}` |

At install time, the Inno wizard collects the SQL + web settings (with a **Test
Connection** button) and then runs `HO_Deploy.exe deploy`, which:
generate config → restore + verify the database → install + start the
`UniNexHO` Windows service → run the health check.

## Building pieces individually

```bat
python -m ho_setup.build backend       :: only HO_Backend
python -m ho_setup.build deploy        :: only HO_Deploy
python -m ho_setup.build uninstall     :: only HO_Uninstall
ISCC installer\HO_Setup.iss            :: only the installer (exes must exist)
```

## Verify the frozen backend

```bat
dist\HO_Backend\HO_Backend.exe selftest
```

Prints `SELFTEST: PASS` when the bundle can import `uvicorn`, `fastapi`,
`pyodbc` and `api.app`. If a module is MISSING, add it to the collect/hidden
lists in [ho_setup/HO_Backend.spec](../ho_setup/HO_Backend.spec). `build.bat`
runs this automatically and fails the build on a bad bundle.

## Build troubleshooting

| Symptom | Fix |
|---------|-----|
| `NEXORA_PLATFORM.bak is missing` | Place the backup in `ho_setup\assets\`. |
| `ISCC.exe not found` | Install Inno Setup 6, or add it to PATH. `build.bat` also checks the default Program Files locations. |
| Backend selftest reports a MISSING module | It is imported dynamically; add it to `_BACKEND_PKGS` / `hiddenimports` in `HO_Backend.spec`. |
| `npm` not found | Install Node.js, or pre-build `frontend\dist` and re-run. |
| pydantic / pydantic_core runtime error | Ensure the build machine's `pydantic` matches the backend's; `collect_all('pydantic')` is already configured. |
