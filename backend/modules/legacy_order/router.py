"""Legacy Order console API.

A web trigger for the two buttons of the old VB.NET OrderManagement app: Sync
and Order Process. Everything here reads and writes the OLD OrderNMC database
and the branch DBs it points at -- NOT NEXORA_PLATFORM's sync.* tables.
"""
from fastapi import APIRouter, HTTPException

from modules.legacy_order import database, repository, service, sync_engine
from modules.legacy_order.schemas import ComparePreviousOrderRequest, CompareSupplierRequest, EmergencyRepairRequest, JobStarted, OrderProcessRequest, StockUpdateRequest, SyncRequest, UpdateOrderQtyRequest, UpdateQtyCheckRequest

router = APIRouter(prefix="/api/legacy-order", tags=["Legacy Order"])


# ---- Legacy DB health & recovery (RECOVERY_PENDING / single-user / repair) ----

@router.get("/db/health")
def db_health():
    """State of the OrderNMC database (ONLINE / RECOVERY_PENDING / single-user...).
    Read-only -- powers the console's DB status card and Recheck button."""
    return database.database_health()


@router.post("/db/recover")
def db_recover():
    """Non-destructive auto-recovery: flip single-user back to MULTI_USER, or
    restart crash recovery for a RECOVERY_PENDING/SUSPECT database. Never loses
    data. This is the 'Auto Recover' button."""
    return database.recover_database(allow_data_loss=False)


@router.post("/db/emergency-repair")
def db_emergency_repair(payload: EmergencyRepairRequest):
    """Last resort: EMERGENCY + DBCC CHECKDB(REPAIR_ALLOW_DATA_LOSS). CAN LOSE
    DATA, so it only runs when the caller explicitly confirms."""
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Emergency repair must be confirmed; it can permanently lose data.",
        )
    return database.recover_database(allow_data_loss=True)


@router.get("/stores")
def list_stores(active_only: bool = True):
    """Branches from OrderNMC.Stores. Credentials are never returned."""
    try:
        stores = repository.list_stores(active_only)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return [
        {
            "store_code": s["store_code"],
            "store_name": s["store_name"],
            "server_name": s["server_name"],
            "database": s["database"],
            "is_active": s["is_active"],
            "last_sync_time": s["last_sync_time"],
            "last_sync_status": s["last_sync_status"],
        }
        for s in stores
    ]


@router.get("/tables")
def list_tables():
    return [
        {"source": src, "destination": dest} for src, dest in sync_engine.TABLE_PLAN
    ]


@router.get("/defaults")
def defaults():
    return {"min_days": service.DEFAULT_MIN_DAYS, "max_days": service.DEFAULT_MAX_DAYS}


@router.post("/sync", response_model=JobStarted)
def start_sync(payload: SyncRequest):
    try:
        return JobStarted(job_id=service.start_sync(payload.store_name, payload.tables))
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        status = 409 if "already running" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc))


@router.post("/order-process", response_model=JobStarted)
def start_order_process(payload: OrderProcessRequest):
    try:
        job_id = service.start_order_process(
            payload.store_name, payload.min_days, payload.max_days, payload.mode
        )
        return JobStarted(job_id=job_id)
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        status = 409 if "already running" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc))


@router.post("/stock-update", response_model=JobStarted)
def start_stock_update(payload: StockUpdateRequest):
    """Push the source ("HO") store's own branch stock into this store's
    central SupplierStock rows -- the web trigger for the Universal Supplier
    Stock Distribution feature, scoped to one store."""
    try:
        job_id = service.start_stock_update(payload.store_name, payload.source_store_name)
        return JobStarted(job_id=job_id)
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        status = 409 if "already running" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc))


@router.get("/jobs")
def list_jobs(limit: int = 20):
    return service.list_jobs(limit)


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/orders/{store_name}")
def order_summary(store_name: str):
    """The current OrderManagement rows for a store -- the VB main grid."""
    try:
        return repository.order_summary(store_name)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/orders/{store_name}/{product_code}")
def update_order_qty(store_name: str, product_code: int, payload: UpdateOrderQtyRequest):
    """Manual review edit -- the VB grid's editable OrderQty cell. Setting 0
    marks a product 'no need' without requiring a supplier order."""
    try:
        updated = repository.update_order_qty(store_name, product_code, payload.order_qty)
        if not updated:
            raise HTTPException(status_code=404, detail="Order row not found")
        return {"store_name": store_name, "product_code": product_code, "order_qty": payload.order_qty}
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/previous-orders/{store_name}")
def previous_orders(store_name: str):
    try:
        return repository.previous_orders(store_name)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/compare-previous-order")
def compare_previous_order(payload: ComparePreviousOrderRequest):
    try:
        if not repository.get_store(payload.store_name):
            raise HTTPException(status_code=404, detail="Store not found")
        return repository.compare_previous_order(payload.store_name, payload.order_id)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/previous-orders/{store_name}/{order_id}/suppliers")
def previous_order_suppliers(store_name: str, order_id: int):
    try:
        return repository.previous_order_suppliers(store_name, order_id)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/previous-orders/{store_name}/{order_id}/suppliers/{supplier_code}/products")
def previous_order_supplier_products(
    store_name: str, order_id: int, supplier_code: str
):
    try:
        return repository.previous_order_supplier_products(
            store_name, order_id, supplier_code
        )
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/compare-previous-order/supplier")
def compare_previous_order_supplier(payload: CompareSupplierRequest):
    try:
        return repository.compare_previous_order_supplier(
            payload.store_name, payload.order_id, payload.supplier_code
        )
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---- Qty Check screen (port of Form1's "Qty Check" process) ----

@router.get("/qty-check/{store_name}")
def qty_check_rows(store_name: str):
    try:
        return repository.qty_check_rows(store_name)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/qty-check/{store_name}/{product_code}")
def update_qty_check(store_name: str, product_code: int, payload: UpdateQtyCheckRequest):
    try:
        result = repository.update_qty_check(store_name, product_code, payload.order_qty)
        if result is None:
            raise HTTPException(status_code=404, detail="Order row not found")
        return result
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/qty-check/{store_name}/{product_code}/purchase-details")
def qty_check_purchase_details(store_name: str, product_code: int, mode: str = "local"):
    try:
        store = repository.get_store(store_name)
        if not store:
            raise HTTPException(status_code=404, detail="Store not found")
        return repository.qty_check_purchase_details(store, product_code, mode)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/qty-check/{store_name}/{product_code}/sales-details")
def qty_check_sales_details(store_name: str, product_code: int, mode: str = "local"):
    try:
        store = repository.get_store(store_name)
        if not store:
            raise HTTPException(status_code=404, detail="Store not found")
        return repository.qty_check_sales_details(store, product_code, mode)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/qty-check/{store_name}/{product_code}/monthly-stats")
def qty_check_monthly_stats(store_name: str, product_code: int, mode: str = "local"):
    try:
        store = repository.get_store(store_name)
        if not store:
            raise HTTPException(status_code=404, detail="Store not found")
        return repository.qty_check_monthly_stats(store, product_code, mode)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/qty-check/{store_name}/{product_code}/order-history")
def qty_check_order_history(store_name: str, product_code: int):
    try:
        return repository.qty_check_order_history(store_name, product_code)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
