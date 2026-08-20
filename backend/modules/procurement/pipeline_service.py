"""End-to-end Procurement pipeline (Master Integration Sprint).

Runs the real-data pipeline for one store, stopping at Workspace generation
(no Supplier Assignment). Reuses the existing orchestration and Decision Engine
— it adds NO business logic. Every stage is timed and logged.

    (Store Sync)  ->  read Last GRN / Last Sale Bill (real sync.*)
                  ->  Create Business Cycle (Start GRN / Start Sale Bill)
                  ->  Create Refresh -> Decision Engine -> VPL -> Working Items
                  ->  Execution summary
"""

import logging
import time

from fastapi import HTTPException

from modules.procurement import orchestration_service
from modules.procurement import platform_source_repository as src

logger = logging.getLogger("procurement.pipeline")


def _trigger_and_wait_sync(tenant_id, store_id):
    """Store Sync stage — enqueue a REAL sync task via the platform sync service.

    Platform sync is agent-mediated and asynchronous (HO enqueues a task; the
    Store Agent polls, executes and completes it). A blocking in-request wait is
    therefore not production-safe, so procurement enqueues the task and runs the
    Decision Engine on the already-synchronized ``sync.*`` data (kept current by
    the platform's sync lifecycle). The enqueued task_id is returned for
    traceability. Enqueue failures are reported, not fatal.
    """
    from modules.sync import runtime_service as sync_runtime
    try:
        result = sync_runtime.create_task({
            "tenant_id": tenant_id, "store_id": store_id,
            "execution_type": "FULL", "sync_mode": "FULL",
        })
        logger.info("Store Sync enqueued tenant=%s store=%s task=%s",
                    tenant_id, store_id, result.get("task_id"))
        return {
            "triggered": True,
            "status": "enqueued",
            "task_id": str(result.get("task_id")),
            "detail": "Sync runs asynchronously via the Store Agent; the engine "
                      "uses the current synced data.",
        }
    except Exception as exc:  # enqueue failure is non-fatal, but reported
        logger.exception("Store Sync enqueue failed tenant=%s store=%s", tenant_id, store_id)
        return {"triggered": False, "status": "error", "detail": str(exc)}


def run(tenant_id, store_id, rolling_days, min_days, max_days, created_by):
    if not store_id:
        raise HTTPException(status_code=400, detail="store_id is required")

    timings = {}
    t0 = time.perf_counter()

    sync_info = _trigger_and_wait_sync(tenant_id, store_id)
    timings["sync_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    # Read real boundaries + telemetry from synced data.
    products_available = src.product_count(tenant_id, store_id)
    last_grn = src.read_last_grn(tenant_id, store_id)
    last_bill = src.read_last_sale_bill(tenant_id, store_id)

    # Create Business Cycle (captures Start GRN / Start Sale Bill).
    t1 = time.perf_counter()
    cycle = orchestration_service.create_business_cycle({
        "tenant_id": tenant_id,
        "store_id": store_id,
        # name is server-authoritative (see orchestration_service.cycle_name).
        "start_grn_number": last_grn,
        "start_sale_bill_number": last_bill,
        "created_by": created_by,
    })
    timings["cycle_ms"] = round((time.perf_counter() - t1) * 1000, 1)

    # Create Refresh -> Decision Engine -> VPL -> Working Items.
    t2 = time.perf_counter()
    refresh = orchestration_service.create_refresh(tenant_id, cycle["cycle_id"], {
        "rolling_days": rolling_days,
        "min_days": min_days,
        "max_days": max_days,
        # snapshot_name is server-authoritative (see orchestration_service.refresh_name).
        "snapshot_grn_number": last_grn,
        "snapshot_sale_bill_number": last_bill,
        "created_by": created_by,
    })
    timings["refresh_engine_ms"] = round((time.perf_counter() - t2) * 1000, 1)
    timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    logger.info(
        "Pipeline complete tenant=%s store=%s cycle=%s refresh=%s products=%s "
        "included=%s working=%s total_ms=%s",
        tenant_id, store_id, cycle["cycle_id"], refresh["refresh_id"],
        refresh["generated_product_count"], refresh["included_count"],
        refresh["working_item_count"], timings["total_ms"],
    )

    return {
        "sync": sync_info,
        "products_available": products_available,
        "start_grn_number": last_grn,
        "start_sale_bill_number": last_bill,
        "cycle_id": cycle["cycle_id"],
        "refresh_id": refresh["refresh_id"],
        "rolling_days": rolling_days,
        "min_days": min_days,
        "max_days": max_days,
        "generated_product_count": refresh["generated_product_count"],
        "included_count": refresh["included_count"],
        "excluded_count": refresh["excluded_count"],
        "working_item_count": refresh["working_item_count"],
        "timings_ms": timings,
    }
