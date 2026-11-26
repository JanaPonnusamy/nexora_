# Daily 180-Day Retention + Fleet-Wide Log/Disk Hygiene — Plan (draft, not yet built)

Status: **planning for the new, larger scope only**. The 180-day retention
*mechanism* itself is already built (`backend/modules/legacy_order/retention.py`
+ `/api/legacy-order/db/retention-preview` and `/db/retention-purge`,
admin-gated, report-first) — this doc is about (a) making it run daily
instead of weekly, and (b) the new fleet-wide log/disk-hygiene ask, which is
materially bigger and needs its own careful rollout.

Owner's exact ask, broken into five pieces:
1. 180-day window check **every day** (not weekly) — purge runs daily on
   OrderNMC/OrderSMS/OrderSuccess, since NEXORA_PLATFORM already holds full
   history.
2. **Every side of the project** (store agent, backend, any other app) —
   log files kept to **3 days only**, not unbounded.
3. Root cause: "one store now log grow and full C drive become not
   usable" — a real incident, store unspecified, needs identifying.
4. **Never install to C: drive in future** — new installs/deployments must
   target a non-system drive.
5. **Auto-grow monitoring** on log/data files, warn when growth is
   abnormal.

---

## 1. What's already confirmed vs. not yet

**Confirmed (read directly from code this session):**
- `database.central_connection_string()` is already tenant-scoped — a
  single retention job naturally covers OrderNMC/OrderSMS/OrderSuccess
  without hardcoding DB names, by running once per tenant.
- `store_agent/main.py` and the rest of `store_agent/` have **no
  `logging.basicConfig`/`FileHandler` found by targeted search** — the
  agent's own Python logging is not obviously the thing filling the C:
  drive. This means the "log grow and full C drive" incident is more
  likely one of: SQLite journal/WAL growth, a cached-config/temp folder
  Storage Sense interacts badly with (see existing memory:
  `store-agent-temp-fernet-fix` — a prior incident where Storage Sense
  deleting temp files broke the agent's fernet key), a Windows Event Log,
  or a different app on that store PC entirely (antivirus, POS software,
  SQL Server's own log).
- **Not yet confirmed**: which store, which folder/file was actually
  growing, and its real size. This needs a live `Get-ChildItem -Recurse |
  Sort Length -Descending` (or similar) on the affected store PC before
  guessing further — diagnosis first, fix second.

**Open question before Phase 2 (log rotation) can be scoped precisely:**
which specific files were the ones that grew? Without that, "add log
rotation everywhere" risks missing the actual offender while adding
rotation to files that were never the problem.

---

## 2. Phase 1 — Daily retention (smallest, already-built mechanism)

Change nothing about `retention.py` itself. Add a daily trigger:
- Simplest: extend the existing Windows Scheduled Task pattern
  (`NexoraIndexMaintenance`, currently weekly Sunday 9AM) with a SECOND,
  daily task that calls `/api/legacy-order/db/retention-purge` (via a
  small PowerShell `Invoke-RestMethod` + superadmin login, same pattern as
  `send_input3.ps1` from the earlier session) once every 24h, for every
  tenant the box hosts.
- Keep the first real run as report-only (`/db/retention-preview`) to see
  actual row counts before the first live purge — this is the one place
  where "don't wait for approval" still yields to "measure the blast
  radius of a new destructive automation before it goes live unattended,"
  consistent with the owner's own earlier confirmed preference for
  report-first retention rollouts.
- After one clean preview + one clean manual purge, register the daily
  scheduled task for real.

## 3. Phase 2 — Diagnose the actual disk-fill incident (before building log rotation)

1. Identify which store had the C: drive incident (owner to name it, or a
   live check across the fleet via Device Controller's remote-terminal
   API — same mechanism used for the earlier .73/.32 maintenance rollout
   — running a top-20-largest-files scan per store PC).
2. Once the actual offending file/folder is known, decide the fix at that
   specific layer (SQLite VACUUM/WAL checkpoint settings, a temp-file
   cleanup exclusion from Storage Sense, an actual log file that needs
   rotation, or something unrelated to this project entirely).
3. Only after that: generalize into a standing "3-day log retention"
   convention for every app side (store agent, backend, remote_order_agent,
   any other service) — implemented as Python's
   `TimedRotatingFileHandler(when="D", backupCount=3)` wherever a
   `logging.FileHandler`/`basicConfig(filename=...)` is later found or
   added, plus a scheduled cleanup pass for any pre-existing unbounded log
   files already on disk at store PCs.

## 4. Phase 3 — "Never install to C: drive" going forward

- Standing rule for all NEW installers/deployment scripts from this point:
  default install target must be a non-system drive (e.g. `D:\Nexora...`
  or wherever the store PC's data drive is), falling back to asking the
  operator to pick a drive rather than silently defaulting to
  `C:\Program Files` or `C:\NexoraMaintenance`-style paths.
- Existing installed locations (already on C: at live stores) are NOT
  migrated retroactively by this rule — that would be its own risky,
  disruptive project. This rule governs future installs only, per the
  same "existing stays, additive only" principle used throughout this
  session's other plans.
- Needs the actual installer script(s) identified before implementing —
  `installer/install_phase_sync_*.py` files exist (seen this session) but
  weren't opened; next step is finding wherever they pick an install path.

## 5. Phase 4 — Auto-grow / abnormal-growth monitoring with warnings

- Reuse the existing `sync/health_monitor.py` WhatsApp-alert pattern
  (confirmed to exist from this session's memory:
  `sync-health-monitor` — already alerts on stale/failing syncs and
  agent-offline) rather than building a new alert channel.
- New check: per store PC (or per monitored SQL Server box), compare
  today's data/log file sizes against yesterday's (or a rolling baseline)
  and flag any file that grew by more than a configurable threshold
  (e.g. >20% or >500MB in a day) as "abnormal growth" — this is a NEW
  metric, not yet collected anywhere, so it needs its own small
  size-history table before alerting logic can run on it.
- Scope question still open: does "auto-grow monitor" mean SQL Server
  data/log file auto-growth events specifically (there's a DMV for that,
  `sys.dm_os_performance_counters` or querying `sys.database_files`
  growth settings), or general disk-space/any-file growth on the store
  PC? These need different implementations — needs the owner's intent
  confirmed before Phase 4 starts (SQL-specific is much smaller scope).

---

## 6. Build order
1. Daily retention schedule (Phase 1) — mechanism already built, just
   needs the daily trigger + one more report-first check per tenant.
2. Diagnose the actual C: drive incident (Phase 2 step 1) — this must
   come before deciding what "3-day log retention everywhere" even
   targets.
3. Generalize log rotation once the real offender is known (Phase 2
   steps 2-3).
4. C:-drive install policy for future installers (Phase 3) — independent,
   can proceed in parallel once the relevant installer scripts are
   located.
5. Auto-grow monitoring (Phase 4) — depends on Phase 2's diagnosis to
   know whether this is a SQL-specific or OS-wide disk metric.

## 7. What stays untouched
- `retention.py`'s existing report-first/admin-gated design — daily
  scheduling does not remove that safety, it just runs it more often.
- No existing store-agent code is modified until the actual disk-fill
  cause is identified — no speculative log-rotation changes landed
  blind.
