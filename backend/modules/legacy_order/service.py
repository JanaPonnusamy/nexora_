"""Job orchestration for the legacy Order console.

Sync and Order Process both take minutes, so they run on a worker thread and the
UI polls a job record -- the web equivalent of the VB BackgroundWorker +
ProgressBar + lblStatus.

Jobs live in memory: a restart loses history, which is the same guarantee the
desktop app gave. Nothing here is a source of truth; OrderNMC is.
"""
import datetime
import logging
import threading
import uuid

from modules.legacy_order import order_process, repository, sync_engine

logger = logging.getLogger(__name__)

_jobs = {}
_lock = threading.Lock()

DEFAULT_MIN_DAYS = 13
DEFAULT_MAX_DAYS = 18


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
    if not store["server_name"] or not store["database"]:
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

    ok, error = repository.test_branch_connection(store)
    if not ok:
        raise ConnectionError(f"Failed to connect to {store['server_name']}: {error}")

    plan = [(s, d) for s, d in sync_engine.TABLE_PLAN if not tables or s in tables]
    if not plan:
        raise ValueError("No known tables selected to sync.")

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

    _update(
        job_id,
        status=status,
        result={"tables": tables},
        error=(f"{len(failed)} table(s) failed: {', '.join(failed)}" if failed else None),
        message=("Sync completed." if not failed
                 else f"Sync finished with {len(failed)} failed table(s)."),
        finished_at=datetime.datetime.now(),
    )


# ----- Order Process ----------------------------------------------------------

def start_order_process(store_name, min_days=None, max_days=None, mode="local"):
    store = _resolve_store(store_name)

    min_days = DEFAULT_MIN_DAYS if min_days is None else min_days
    max_days = DEFAULT_MAX_DAYS if max_days is None else max_days
    if min_days <= 0 or max_days <= 0:
        raise ValueError("Min days and max days must be positive.")
    if min_days > max_days:
        raise ValueError("Min days cannot be greater than max days.")
    if mode not in ("local", "remote"):
        raise ValueError("Mode must be 'local' or 'remote'.")

    running = _running_job_kind(store_name)
    if running:
        raise ValueError(
            f"A {running} job is already running for '{store_name}'. Wait for it to finish."
        )

    # Order Process always begins with a fresh full branch sync.
    ok, error = repository.test_branch_connection(store)
    if not ok:
        raise ConnectionError(f"Failed to connect to {store['server_name']}: {error}")

    plan = list(sync_engine.TABLE_PLAN)
    job_id = _new_job("order", store_name, len(plan) + 3)
    threading.Thread(
        target=_run_sync_then_order,
        args=(job_id, store, plan, min_days, max_days, mode),
        daemon=True,
    ).start()
    return job_id


def _run_sync_then_order(job_id, store, plan, min_days, max_days, mode):
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

    if failed:
        _update(
            job_id, status="failed", result={"tables": tables},
            error=f"Order process stopped because sync failed: {', '.join(failed)}",
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
        result = order_process.run_order_process(store, min_days, max_days, mode, report)
        result["tables"] = tables
        _update(
            job_id, status="completed", step=base_step + 3, result=result,
            message=f"Sync and order processing completed ({result['rows']} rows).",
            finished_at=datetime.datetime.now(),
        )
    except Exception as exc:
        logger.exception("legacy order process failed after sync")
        _update(
            job_id, status="failed", result={"tables": tables}, error=str(exc),
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


def _run_order(job_id, store, min_days, max_days, mode):
    step = {"n": 0}

    def report(message):
        step["n"] += 1
        _update(job_id, step=min(step["n"], 3), message=message)

    try:
        result = order_process.run_order_process(store, min_days, max_days, mode, report)
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
