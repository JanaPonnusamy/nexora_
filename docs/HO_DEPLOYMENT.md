# UniNex HO Deployment Runbook

How to deploy the UniNex Head Office to a **new tenant PC** with `HO_Setup.exe`.
Goal: zero manual database setup beyond installing SQL Server.

## Prerequisites on the tenant machine

| Requirement | Why |
|-------------|-----|
| Windows 10/11 or Windows Server 2019+ | target OS |
| **SQL Server** installed and running (Express is fine) | hosts `NEXORA_PLATFORM` |
| **ODBC Driver 17 for SQL Server** | used by the backend + installer |
| Administrator rights | to register the Windows service |
| TCP port `8000` free (or chosen alternative) | backend API + frontend |

> The installer assumes SQL Server is on the **same machine** as HO (it restores
> the `.bak` from a local path the SQL service account can read).

## Deployment workflow

```
Fresh Windows machine
   |
Install SQL Server  +  ODBC Driver 17        (manual, prerequisites)
   |
Copy HO_Setup.exe to the machine
   |
Run HO_Setup.exe as Administrator
   |
 Step 4  Configure + Test SQL connection
   |
 Step 5  Restore NEXORA_PLATFORM.bak         (Replace/Cancel if it already exists)
   |
 Step 6  Generate production configuration
   |
 Step 7  Install backend files
   |
 Step 8  Install + start Windows service  (UniNexHO, auto-start)
   |
 Step 9  Deploy frontend + point at API
   |
 Step 10 Health check + summary
   |
Production Ready
```

## Step-by-step (Inno wizard)

1. **Copy** `HO_Setup.exe` to the tenant PC.
2. **Right-click → Run as administrator.**
3. **License** — accept the agreement.
4. **Select destination folder** — default `C:\Program Files\UniNex\HO`.
5. **SQL Server Authentication** — choose *SQL Server Authentication* (username
   and password) or *Windows Authentication* (trusted connection).
6. **SQL Server Configuration**
   - *Instance*: e.g. `localhost`, `.\SQLEXPRESS`, or `localhost\SQLEXPRESS`.
   - *Database name*: `NEXORA_PLATFORM` (default).
   - *Username / Password* (SQL auth only).
   - Click **Test Connection** — confirm it succeeds before continuing.
7. **Web Server Settings** — *Server address* (hostname or IP browsers use to
   reach this machine; defaults to the computer name) and *Port* (default 8000).
8. **Ready to Install → Install.** The installer copies all files, then runs the
   deployment automatically (a console window shows progress):
   - If a database of that name **already exists**, it asks *Replace?* — Yes
     overwrites it (`WITH REPLACE`, single-user toggle), No cancels the install.
   - generate config → **restore + verify `NEXORA_PLATFORM.bak`** → install +
     start the `UniNexHO` service → run the health check (SQL, DB, service, API
     `/health`, frontend `/`).
   - Any failure aborts with a clear message pointing at the logs.
9. **Finish.** HO is live at `http://<server-address>:<port>`.

> Installer log: `%TEMP%\Setup Log*.txt` (Inno) and the deploy console output.
> Backend log: `{app}\logs\backend.log`.

## What gets installed

```
C:\Program Files\UniNex\HO\
   HO_Backend.exe            Windows-service host (embedded Python + backend)
   _internal\                PyInstaller runtime
   HO_Uninstall.exe
   config\
      ho.env                 DB connection, API/frontend URL, paths
      settings.json          full resolved configuration (audit)
   frontend\                 production SPA + config.js (API endpoint)
   logs\                     backend.log
   uploads\
   backups\                  the restored NEXORA_PLATFORM.bak
```

The Windows service **UniNexHO** is registered with:
- Startup type **Automatic** (starts after Windows boot),
- **Restart-on-failure** (3 attempts, 60 s apart),
- account **LocalSystem**.

## Configuration reference (`config\ho.env`)

| Variable | Meaning |
|----------|---------|
| `DB_SERVER` / `DB_DATABASE` / `DB_DRIVER` | SQL connection |
| `DB_AUTH_MODE` = `SQL` \| `WINDOWS` | authentication |
| `DB_USERNAME` / `DB_PASSWORD` | SQL auth only |
| `UNINEX_API_URL` | base URL baked into the SPA's `/config.js` |
| `UNINEX_FRONTEND_DIR` | folder the backend serves the SPA from |
| `UNINEX_CORS_ORIGINS` | allowed origins (same-origin in default deploy) |
| `UNINEX_HOST` / `UNINEX_PORT` | bind address of the service |
| `UNINEX_LOG_PATH` / `UNINEX_UPLOAD_PATH` | writable paths |

The backend reads these via `backend/config/database.py` and
`backend/api/app.py`. The Windows-service host loads `ho.env` before the app
imports, so changing a value and restarting the service (`sc stop/start
UniNexHO`) re-applies it.

## Operations

```
sc query UniNexHO          # state
sc stop  UniNexHO
sc start UniNexHO
```
Logs: `C:\Program Files\UniNex\HO\logs\backend.log` and the Windows Event Log
(Application, source `UniNexHO`). Installer logs: `%TEMP%\UniNex\HO_Setup_*.log`.

## Uninstall

Use **Settings → Apps & features → UniNex HO → Uninstall**, the Start-menu
*Uninstall UniNex HO*, or `{app}\HO_Uninstall.exe`. Uninstalling stops and
removes the `UniNexHO` service, then deletes the application files. The **SQL
database is preserved**.

To also drop the database, run the standalone uninstaller explicitly:
`"{app}\HO_Uninstall.exe" /silent /dropdb` (or tick *Also DROP the SQL database*
in its GUI). This is irreversible.

## Troubleshooting

| Symptom | Action |
|---------|--------|
| Test Connection fails: *ODBC driver not found* | Install **ODBC Driver 17 for SQL Server**. |
| Test Connection fails: *Login failed* | Check SQL username/password, or use Windows auth. |
| Test Connection fails: *Cannot reach SQL Server* | Verify the instance name and that the SQL service + TCP/IP are enabled. |
| Restore fails | Ensure the SQL service account can read the `.bak` under `...\HO\backups\`; confirm enough disk space. |
| Service won't reach RUNNING | Check `logs\backend.log` and Event Log; confirm port 8000 is free and the DB restored. |
| Browser can't reach the app from another PC | Set *Server address* to the machine's LAN IP/hostname and open the firewall for the port. |
