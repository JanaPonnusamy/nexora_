"""Job orchestration for the legacy Order console.

Sync and Order Process both take minutes, so they run on a worker thread and the
UI polls a job record -- the web equivalent of the VB BackgroundWorker +
ProgressBar + lblStatus.

Jobs live in memory: a restart loses history, which is the same guarantee the
desktop app gave. Nothing here is a source of truth; OrderNMC is.
"""
import datetime
import logging
import os
import threading
import uuid

from modules.legacy_order import database, order_process, repository, sync_engine

logger = logging.getLogger(__name__)

_jobs = {}
_lock = threading.Lock()

DEFAULT_MIN_DAYS = 13
DEFAULT_MAX_DAYS = 18

# Warehouse stores (e.g. NMW) get the warehouse order query: demand counts
# Transfer-Out to branches, not just retail billing (see sql/order_warehouse.sql).
# Which stores are warehouses, their recency window, and their default Min/Max
# days are all env-overridable; defaults match how NMW has historically been
# ordered (90-day average, ~32/35 day cover).
WAREHOUSE_STORES = {
    s.strip().upper()
    for s in os.getenv("LEGACY_WAREHOUSE_STORES", "NMW").split(",")
    if s.strip()
}
WAREHOUSE_RECENCY_DAYS = int(os.getenv("LEGACY_WAREHOUSE_RECENCY_DAYS", "30"))
WAREHOUSE_MIN_DAYS = int(os.getenv("LEGACY_WAREHOUSE_MIN_DAYS", "32"))
WAREHOUSE_MAX_DAYS = int(os.getenv("LEGACY_WAREHOUSE_MAX_DAYS", "35"))


def is_warehouse_store(store_name):
    """True if this store should use the warehouse order query (Transfer-Out
    demand + configurable recency) instead of the retail query."""
    return bool(store_name) and store_name.strip().upper() in WAREHOUSE_STORES


# Agent-synced stores (e.g. NMV) have NO direct branch SQL connection from HO:
# their POS data arrives via the NMV Integration agent (outbound HTTPS) and is
# already in the central OrderNMC copy. For these stores the Order Process runs
# entirely against that central copy -- no branch connection test, no pre-order
# branch pull, and the header watermark reads come from central (StoreName-
# scoped). Env-overridable, same shape as WAREHOUSE_STORES. The five LAN stores
# (NMA/NMW/NMC/NMG/NMS) are NOT in this set, so their path is unchanged.
AGENT_SYNCED_STORES = {
    s.strip().upper()
    for s in os.getenv("LEGACY_AGENT_SYNCED_STORES", "NMV").split(",")
    if s.strip()
}


def is_agent_synced_store(store_name):
    """True if this store's data arrives via the NMV Integration agent rather
    than a direct HO->branch SQL pull (so the Order Process must read the
    already-synced central copy, never the branch)."""
    return bool(store_name) and store_name.strip().upper() in AGENT_SYNCED_STORES


def _new_job(kind, store_name, total_steps):
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "kind": kind,
            "store_name": store_name,
            "status": "running",
            "step": 0,
            "total_steps": total_steps,
            "message": "Starting...",
            "log": [],
            "result": None,
            "error": None,
            "warning": None,
            "started_at": datetime.datetime.now(),
            "finished_at": None,
        }
    return job_id


def _update(job_id, **fields):
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        message = fields.get("message")
        if message:
            job["log"].append({
                "at": datetime.datetime.now().isoformat(timespec="seconds"),
                "message": message,
            })
        job.update(fields)


def get_job(job_id):
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def list_jobs(limit=20):
    with _lock:
        jobs = sorted(_jobs.values(), key=lambda j: j["started_at"], reverse=True)
        return [dict(j) for j in jobs[:limit]]


def _running_job_kind(store_name):
    """Kind of job already running for this store, if any."""
    with _lock:
        for job in _jobs.values():
            if job["store_name"] == store_name and job["status"] == "running":
                return job["kind"]
    return None


def _resolve_store(store_name):
    store = repository.get_store(store_name)
    if not store:
        raise ValueError(f"Store '{store_name}' is not configured in OrderNMC.Stores.")
    # Agent-synced stores (NMV) legitimately have no branch server/database -- HO
    # never connects to them directly; their data arrives via the NMV Integration
    # agent. LAN stores still require a configured source DB (unchanged).
    if not is_agent_synced_store(store_name) and (
        not store["server_name"] or not store["database"]
    ):
        raise ValueError(
            f"Store '{store_name}' has no source server/database configured."
        )
    return store


# ----- Sync -------------------------------------------------------------------

def start_sync(store_name, tables=None):
    store = _resolve_store(store_name)

    running = _running_job_kind(store_name)
    if running:
        raise ValueError(
            f"A {running} job is already running for '{store_name}'. Wait for it to finish."
        )

    plan = [(s, d) for s, d in sync_engine.TABLE_PLAN if not tables or s in tables]
    if not plan:
        raise ValueError("No known tables selected to sync.")

    # Agent-synced stores (NMV) have no branch to pull: their live data is in
    # NEXORA_PLATFORM.sync.* (delivered by the platform sync pipeline). Copy that
    # into central OrderNMC, filtered by the store's platform store_id.
    if is_agent_synced_store(store_name):
        store_id = database.platform_store_id(store["store_name"])
        if not store_id:
            raise ValueError(
                f"'{store_name}' has no platform store_id in NEXORA_PLATFORM.dbo.stores."
            )
        job_id = _new_job("sync", store_name, len(plan))
        threading.Thread(
            target=_run_agent_sync, args=(job_id, store, store_id, plan), daemon=True
        ).start()
        return job_id

    ok, error = repository.test_branch_connection(store)
    if not ok:
        raise ConnectionError(f"Failed to connect to {store['server_name']}: {error}")

    job_id = _new_job("sync", store_name, len(plan))
    threading.Thread(
        target=_run_sync, args=(job_id, store, plan), daemon=True
    ).start()
    return job_id


def _run_sync(job_id, store, plan):
    source_cs = order_process.database.branch_connection_string(
        store["server_name"], store["database"], store["username"], store["password"]
    )
    dest_cs = order_process.database.central_connection_string()

    tables, failed = [], []
    for index, (src, dest) in enumerate(plan):
        _update(job_id, step=index, message=f"Starting sync: {src}")
        try:
            rows, batch_errors = sync_engine.sync_table(
                source_cs, dest_cs, src, dest, store["store_name"]
            )
            if batch_errors:
                failed.append(src)
                tables.append({"table": src, "destination": dest, "rows": rows,
                               "status": "partial", "error": "; ".join(batch_errors)})
                _update(job_id, step=index + 1,
                        message=f"Partial: {src} -- {len(batch_errors)} batch(es) failed")
            else:
                tables.append({"table": src, "destination": dest, "rows": rows,
                               "status": "ok", "error": None})
                _update(job_id, step=index + 1,
                        message=f"Completed: {src} ({rows} rows)")
        except Exception as exc:
            # VB logged and carried on to the next table, so one bad table did not
            # abandon the rest. Same here -- but the job ends 'failed', because a
            # partial sync that reports success is how stale orders get placed.
            logger.exception("legacy sync failed for %s", src)
            failed.append(src)
            tables.append({"table": src, "destination": dest, "rows": 0,
                           "status": "error", "error": str(exc)})
            _update(job_id, step=index + 1, message=f"Error syncing {src}: {exc}")

    status = "failed" if failed else "completed"
    try:
        repository.mark_sync_result(
            store["store_name"], "SUCCESS" if not failed else "FAILED"
        )
    except Exception:
        logger.exception("could not update Stores.LastSyncStatus")

    warning = None
    try:
        warning = repository.stale_sale_bill_warning(store["store_name"])
    except Exception:
        logger.exception("could not check last sale bill freshness")

    _update(
        job_id,
        status=status,
        result={"tables": tables},
        error=(f"{len(failed)} table(s) failed: {', '.join(failed)}" if failed else None),
        warning=warning,
        message=("Sync completed." if not failed
                 else f"Sync finished with {len(failed)} failed table(s)."),
        finished_at=datetime.datetime.now(),
    )


# ----- Order Process ----------------------------------------------------------

def start_order_process(store_name, min_days=None, max_days=None, mode="local"):
    store = _resolve_store(store_name)
    warehouse = is_warehouse_store(store_name)
    agent_synced = is_agent_synced_store(store_name)

    # Warehouse Min/Max default to the warehouse profile (not the retail 13/18).
    default_min = WAREHOUSE_MIN_DAYS if warehouse else DEFAULT_MIN_DAYS
    default_max = WAREHOUSE_MAX_DAYS if warehouse else DEFAULT_MAX_DAYS
    min_days = default_min if min_days is None else min_days
    max_days = default_max if max_days is None else max_days
    if min_days <= 0 or max_days <= 0:
        raise ValueError("Min days and max days must be positive.")
    if min_days > max_days:
        raise ValueError("Min days cannot be greater than max days.")
    if mode not in ("local", "remote"):
        raise ValueError("Mode must be 'local' or 'remote'.")
    # The warehouse query is StoreName-scoped and must read the central copy.
    if warehouse:
        mode = "local"
    recency_days = WAREHOUSE_RECENCY_DAYS if warehouse else 10

    running = _running_job_kind(store_name)
    if running:
        raise ValueError(
            f"A {running} job is already running for '{store_name}'. Wait for it to finish."
        )

    # Agent-synced stores (NMV) have no branch to pull. Their live data lands in
    # NEXORA_PLATFORM.sync.* via the platform sync pipeline, so the Order Process
    # begins with a fresh platform->central copy (filtered by store_id) and then
    # generates the order against the central copy -- mirroring the LAN path,
    # just with a different sync source. LAN stores keep the branch path below.
    if agent_synced:
        store_id = database.platform_store_id(store["store_name"])
        if not store_id:
            raise ValueError(
                f"'{store_name}' has no platform store_id in NEXORA_PLATFORM.dbo.stores."
            )
        plan = list(sync_engine.TABLE_PLAN)
        job_id = _new_job("order", store_name, len(plan) + 3)
        threading.Thread(
            target=_run_agent_sync_then_order,
            args=(job_id, store, store_id, plan, min_days, max_days, mode,
                  warehouse, recency_days),
            daemon=True,
        ).start()
        return job_id

    # Order Process always begins with a fresh full branch sync.
    ok, error = repository.test_branch_connection(store)
    if not ok:
        raise ConnectionError(f"Failed to connect to {store['server_name']}: {error}")

    plan = list(sync_engine.TABLE_PLAN)
    job_id = _new_job("order", store_name, len(plan) + 3)
    threading.Thread(
        target=_run_sync_then_order,
        args=(job_id, store, plan, min_days, max_days, mode, warehouse, recency_days),
        daemon=True,
    ).start()
    return job_id


def _run_sync_then_order(job_id, store, plan, min_days, max_days, mode,
                         is_warehouse=False, recency_days=10):
    """One durable job: full sync must succeed before order generation."""
    source_cs = order_process.database.branch_connection_string(
        store["server_name"], store["database"], store["username"], store["password"]
    )
    dest_cs = order_process.database.central_connection_string()
    tables, failed = [], []

    for index, (src, dest) in enumerate(plan):
        _update(job_id, step=index, message=f"Syncing {src} before order process...")
        try:
            rows, batch_errors = sync_engine.sync_table(
                source_cs, dest_cs, src, dest, store["store_name"]
            )
            if batch_errors:
                failed.append(src)
                tables.append({"table": src, "destination": dest, "rows": rows,
                               "status": "partial", "error": "; ".join(batch_errors)})
            else:
                tables.append({"table": src, "destination": dest, "rows": rows,
                               "status": "ok", "error": None})
            _update(job_id, step=index + 1, message=f"Synced {src} ({rows} rows).")
        except Exception as exc:
            logger.exception("pre-order sync failed for %s", src)
            failed.append(src)
            tables.append({"table": src, "destination": dest, "rows": 0,
                           "status": "error", "error": str(exc)})
            _update(job_id, step=index + 1, message=f"Error syncing {src}: {exc}")

    try:
        repository.mark_sync_result(store["store_name"], "FAILED" if failed else "SUCCESS")
    except Exception:
        logger.exception("could not update Stores.LastSyncStatus")

    warning = None
    try:
        warning = repository.stale_sale_bill_warning(store["store_name"])
    except Exception:
        logger.exception("could not check last sale bill freshness")

    if failed:
        _update(
            job_id, status="failed", result={"tables": tables},
            error=f"Order process stopped because sync failed: {', '.join(failed)}",
            warning=warning,
            message="Pre-order sync failed. Order generation was not started.",
            finished_at=datetime.datetime.now(),
        )
        return

    base_step = len(plan)
    step = {"n": 0}

    def report(message):
        step["n"] += 1
        _update(job_id, step=min(base_step + step["n"], base_step + 3), message=message)

    try:
        _update(job_id, step=base_step, message="Sync completed. Starting order process...")
        result = order_process.run_order_process(
            store, min_days, max_days, mode, report,
            is_warehouse=is_warehouse, recency_days=recency_days,
        )
        result["tables"] = tables
        _update(
            job_id, status="completed", step=base_step + 3, result=result,
            warning=warning,
            message=f"Sync and order processing completed ({result['rows']} rows).",
            finished_at=datetime.datetime.now(),
        )
    except Exception as exc:
        logger.exception("legacy order process failed after sync")
        _update(
            job_id, status="failed", result={"tables": tables}, error=str(exc),
            warning=warning,
            message=f"Sync completed, but order processing failed: {exc}",
            finished_at=datetime.datetime.now(),
        )


# ----- Agent-synced sync (platform sync.* -> central OrderNMC) ----------------

def _run_platform_sync(job_id, store, store_id, plan):
    """Copy an agent-synced store's data from NEXORA_PLATFORM.sync.* (filtered by
    store_id) into central OrderNMC, reusing the legacy sync engine's watermark +
    StoreName stamp + MERGE. Returns (tables, failed)."""
    # HO base rule: correct this node's clock from internet time before syncing
    # (the agent's signed pulls and every SYSUTCDATETIME stamp depend on it).
    try:
        from modules.ho_ops.clock import ensure_ho_clock
        ensure_ho_clock(reason="before-sync")
    except Exception:
        logger.exception("pre-sync clock check failed (continuing)")

    dest_cs = database.central_connection_string()
    platform_cs = database.platform_connection_string()
    tables, failed = [], []
    for index, (src, dest) in enumerate(plan):
        _update(job_id, step=index, message=f"Syncing {src} from platform sync.* ...")
        try:
            rows, batch_errors = sync_engine.sync_table(
                platform_cs, dest_cs, src, dest, store["store_name"], store_id=store_id
            )
            if batch_errors:
                failed.append(src)
                tables.append({"table": src, "destination": dest, "rows": rows,
                               "status": "partial", "error": "; ".join(batch_errors)})
            else:
                tables.append({"table": src, "destination": dest, "rows": rows,
                               "status": "ok", "error": None})
            _update(job_id, step=index + 1, message=f"Synced {src} ({rows} rows).")
        except Exception as exc:
            logger.exception("platform sync failed for %s", src)
            failed.append(src)
            tables.append({"table": src, "destination": dest, "rows": 0,
                           "status": "error", "error": str(exc)})
            _update(job_id, step=index + 1, message=f"Error syncing {src}: {exc}")

    try:
        repository.mark_sync_result(store["store_name"], "FAILED" if failed else "SUCCESS")
    except Exception:
        logger.exception("could not update Stores.LastSyncStatus")
    return tables, failed


def _run_agent_sync(job_id, store, store_id, plan):
    """Sync-only job for an agent-synced store (the /sync trigger)."""
    tables, failed = _run_platform_sync(job_id, store, store_id, plan)
    total = sum(t["rows"] for t in tables)
    warning = None
    try:
        warning = repository.stale_sale_bill_warning(store["store_name"])
    except Exception:
        logger.exception("could not check last sale bill freshness")
    _update(
        job_id,
        status=("failed" if failed else "completed"),
        result={"tables": tables},
        error=(f"{len(failed)} table(s) failed: {', '.join(failed)}" if failed else None),
        warning=warning,
        message=("Sync completed." if not failed
                 else f"Sync finished with {len(failed)} failed table(s)."),
        finished_at=datetime.datetime.now(),
    )


def _run_agent_sync_then_order(job_id, store, store_id, plan, min_days, max_days,
                               mode, is_warehouse=False, recency_days=10):
    """One durable job for an agent-synced store: platform sync must succeed
    before order generation (same guarantee as the LAN sync-then-order path)."""
    tables, failed = _run_platform_sync(job_id, store, store_id, plan)

    warning = None
    try:
        warning = repository.stale_sale_bill_warning(store["store_name"])
    except Exception:
        logger.exception("could not check last sale bill freshness")

    if failed:
        _update(
            job_id, status="failed", result={"tables": tables},
            error=f"Order process stopped because sync failed: {', '.join(failed)}",
            warning=warning,
            message="Platform sync failed. Order generation was not started.",
            finished_at=datetime.datetime.now(),
        )
        return

    base_step = len(plan)
    step = {"n": 0}

    def report(message):
        step["n"] += 1
        _update(job_id, step=min(base_step + step["n"], base_step + 3), message=message)

    try:
        _update(job_id, step=base_step, message="Sync completed. Starting order process...")
        result = order_process.run_order_process(
            store, min_days, max_days, mode, report,
            is_warehouse=is_warehouse, is_agent_synced=True, recency_days=recency_days,
        )
        result["tables"] = tables
        _update(
            job_id, status="completed", step=base_step + 3, result=result,
            warning=warning,
            message=f"Sync and order processing completed ({result['rows']} rows).",
            finished_at=datetime.datetime.now(),
        )
    except Exception as exc:
        logger.exception("agent order process failed after sync")
        _update(
            job_id, status="failed", result={"tables": tables}, error=str(exc),
            warning=warning,
            message=f"Sync completed, but order processing failed: {exc}",
            finished_at=datetime.datetime.now(),
        )


# ----- Stock Update (internal supplier distribution) --------------------------

def start_stock_update(store_name, source_store_name="NMW"):
    """Push ``source_store_name``'s own branch stock into this store's
    SupplierStock rows (central OrderNMC.SupplierStock), same as running the
    Excel import but sourced live from the HO branch instead of a file."""
    store = _resolve_store(store_name)
    if store_name == source_store_name:
        raise ValueError(f"'{store_name}' is the source store; nothing to update.")
    source_store = _resolve_store(source_store_name)
    if not store["ho_code"]:
        raise ValueError(
            f"'{store_name}' has no Ho_code configured in dbo.Stores -- "
            f"don't know what supplier code its own order screen uses for {source_store_name}."
        )

    running = _running_job_kind(store_name)
    if running:
        raise ValueError(
            f"A {running} job is already running for '{store_name}'. Wait for it to finish."
        )

    ok, error = repository.test_branch_connection(source_store)
    if not ok:
        raise ConnectionError(f"Failed to connect to source store '{source_store_name}': {error}")

    job_id = _new_job("stock", store_name, 2)
    threading.Thread(
        target=_run_stock_update, args=(job_id, store, source_store), daemon=True
    ).start()
    return job_id


def _run_stock_update(job_id, store, source_store):
    try:
        _update(job_id, step=0, message=f"Reading stock from {source_store['store_name']}...")
        rows = repository.branch_stock(source_store)
        _update(job_id, step=1, message=f"Read {len(rows)} products. Updating {store['store_name']}'s supplier stock...")
        # suppliercode is THIS store's own code for the source ("HO") supplier
        # (dbo.Stores.Ho_code), not the source store's name -- NMS/NMA file it
        # under '94', NMC under 'ST_2', NMG under '99', etc.
        inserted = repository.replace_supplier_stock(store["store_name"], store["ho_code"], rows)
        _update(
            job_id, status="completed", step=2,
            result={"rows": inserted, "source_store": source_store["store_name"], "supplier_code": store["ho_code"]},
            message=f"Supplier stock updated ({inserted} rows from {source_store['store_name']}, filed as supplier '{store['ho_code']}').",
            finished_at=datetime.datetime.now(),
        )
    except Exception as exc:
        logger.exception("legacy stock update failed")
        _update(
            job_id, status="failed", error=str(exc),
            message=f"Stock update failed: {exc}",
            finished_at=datetime.datetime.now(),
        )


def _run_order(job_id, store, min_days, max_days, mode, is_warehouse=False,
               is_agent_synced=False, recency_days=10):
    step = {"n": 0}

    def report(message):
        step["n"] += 1
        _update(job_id, step=min(step["n"], 3), message=message)

    try:
        result = order_process.run_order_process(
            store, min_days, max_days, mode, report,
            is_warehouse=is_warehouse, is_agent_synced=is_agent_synced,
            recency_days=recency_days,
        )
        _update(
            job_id,
            status="completed",
            step=3,
            result=result,
            message=f"Order processing completed ({result['rows']} rows).",
            finished_at=datetime.datetime.now(),
        )
    except Exception as exc:
        logger.exception("legacy order process failed")
        _update(
            job_id,
            status="failed",
            error=str(exc),
            message=f"Order processing failed: {exc}",
            finished_at=datetime.datetime.now(),
        )
