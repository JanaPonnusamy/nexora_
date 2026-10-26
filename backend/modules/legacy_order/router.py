"""Legacy Order console API.

A web trigger for the two buttons of the old VB.NET OrderManagement app: Sync
and Order Process. Everything here reads and writes the OLD OrderNMC database
and the branch DBs it points at -- NOT NEXORA_PLATFORM's sync.* tables. This
is a platform-ops console (DB recovery, sync jobs) with no per-tenant model
of its own, so it's gated to super admin / platform users only rather than
tenant-scoped like the rest of the API.
"""
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from config.database import get_connection
from dependencies.auth import get_current_user
from dependencies.store_scope import has_unrestricted_scope
from modules.legacy_order import database, order_export, repository, rulebook_order, service, sync_engine
from modules.legacy_order.schemas import AssignSupplierRequest, AutoAssignRequest, OrderEngineRequest, ComparePreviousOrderRequest, CompareSupplierRequest, EmergencyRepairRequest, ExportOrderRequest, ExportPendingOrderRequest, JobStarted, OrderProcessRequest, RestoreBackupOrderRequest, SkipProductRequest, StockUpdateRequest, SupplierCodeRequest, SyncRequest, UpdateOrderQtyRequest, UpdateQtyCheckRequest, UpdateRemarksRequest, WorkflowActionRequest


def _header_value(value) -> str:
    # h11 rejects a header value with leading/trailing whitespace and Starlette
    # can only encode latin-1. OrderNMC supplier names carry trailing padding
    # ('PURANI HOSPITAL SUPPLIES LTD  (CBM) '), and a rejected header aborts the
    # response after the 200 is logged -- the client sees a dropped connection
    # ("Unable to reach the server") instead of the file.
    text = " ".join(str(value or "").split())
    return text.encode("latin-1", "replace").decode("latin-1")


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if not has_unrestricted_scope(current_user):
        raise HTTPException(status_code=403, detail="Legacy Order console is restricted to platform admins.")
    return current_user


# Read-only, store-scoped order-VIEW paths a non-admin store user may GET. These
# are the "order details" views the remote-store (NMV) purchase manager needs to
# see their own order after it is processed in HO's OrderNMC. Everything else
# (DB recovery, sync/order-process/stock-update triggers, supplier assignment,
# export, workflow finalize/reopen, qty edits) stays admin-only: those are POSTs
# (blocked below for non-admins) and additionally carry their own Depends(
# require_admin), so this relaxation can never expose a mutating path.
_VIEWER_READ_PATHS = (
    re.compile(r"^/api/legacy-order/orders/[^/]+(/.*)?$"),
    re.compile(r"^/api/legacy-order/qty-check/[^/]+(/.*)?$"),
    re.compile(r"^/api/legacy-order/pending-order/[^/]+$"),
    re.compile(r"^/api/legacy-order/suppliers/[^/]+$"),
    re.compile(r"^/api/legacy-order/previous-orders/[^/]+(/.*)?$"),
)

# /stores has no {store_name} path param to check ownership against -- both the
# web and Electron Order Workspace call it unconditionally to populate the
# store picker before a store_name is even known. Let a non-admin store user
# through here too; list_stores() itself filters the response down to just
# their own store (see there), so this can't leak other stores' existence.
_NO_PARAM_READ_PATHS = (
    re.compile(r"^/api/legacy-order/stores$"),
)


# Interactive order mutations a non-admin STORE user may perform on THEIR OWN
# store -- the remote-store purchase manager working their own order from
# outside the LAN via the Order Management desktop client. Each carries a
# {store_name} path param that _user_owns_store checks, so a store user can
# only ever touch their own store(s). Everything NOT in this set (or in
# _PM_WRITE_PATHS below) stays admin-only: sync, order-process, stock-update,
# DB recovery/repair, and the previous-order compares (their store_name is in
# the body, not the path, so request.path_params has none -> ownership check
# can't pass).
_STORE_WRITE_PATHS = (
    re.compile(r"^/api/legacy-order/orders/[^/]+/\d+$"),         # PATCH OrderQty
    re.compile(r"^/api/legacy-order/orders/[^/]+/\d+/remarks$"), # PATCH Remarks
    re.compile(r"^/api/legacy-order/orders/[^/]+/\d+/assign$"),  # POST assign/unassign
    re.compile(r"^/api/legacy-order/orders/[^/]+/export$"),      # POST export
    re.compile(r"^/api/legacy-order/orders/[^/]+/export-pending$"),  # POST pending export (read-only)
    re.compile(r"^/api/legacy-order/orders/[^/]+/unavailable/remove$"),  # POST stock-out bulk remove
    re.compile(r"^/api/legacy-order/orders/[^/]+/auto-assign$"),  # POST bulk assign (best margin)
    re.compile(r"^/api/legacy-order/qty-check/[^/]+/\d+$"),      # PATCH qty-check review
    re.compile(r"^/api/legacy-order/qty-check/[^/]+/\d+/skip$"),  # POST skip (Procurement Esc)
)

# Order workflow finalize/reopen: purchase-manager logins only (not every store
# user), on a store they are assigned to -- owner ruling 2026-10-26 "enable
# procurement for PM users". Handlers use require_admin_or_store_pm.
_PM_WRITE_PATHS = (
    re.compile(r"^/api/legacy-order/orders/[^/]+/workflow/(finalize|reopen)$"),
)


def _is_purchase_manager(user: dict) -> bool:
    return any("purchase" in str(r or "").lower() for r in (user.get("role_names") or []))


def _user_store_codes(user: dict) -> set:
    """Every store the user is assigned to (dbo.user_store_roles), not just the
    JWT's primary-role store -- a PM bound to several stores (e.g. NMCPM, NMHO)
    must reach each of them. Cached on the user dict for the request."""
    cached = user.get("_legacy_store_codes")
    if cached is not None:
        return cached
    codes = {str(user.get("store_code") or "").strip().upper()} - {""}
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT s.store_code FROM dbo.user_store_roles usr "
                "JOIN dbo.stores s ON s.store_id = usr.store_id "
                "WHERE usr.user_id = TRY_CAST(? AS uniqueidentifier) AND usr.is_active = 1",
                (str(user.get("sub") or ""),),
            )
            codes |= {str(row[0] or "").strip().upper() for row in cur.fetchall()} - {""}
        finally:
            conn.close()
    except Exception:
        pass  # fall back to the primary store only
    user["_legacy_store_codes"] = codes
    return codes


def _user_owns_store(user: dict, store_name: str) -> bool:
    """A non-admin store user is locked to the stores they are assigned to.
    store_name here is the OrderNMC StoreName, which equals the platform
    store_code (globally unique)."""
    return str(store_name or "").strip().upper() in _user_store_codes(user)


def require_order_console_access(request: Request, current_user: dict = Depends(get_current_user)) -> dict:
    """Platform admins get the whole console. A non-admin user assigned to a
    store may ALSO work that one store's order from outside the LAN: GET its
    read-only order views, and perform the interactive order actions on it
    (edit OrderQty / qty-check review, assign/unassign a supplier, export).
    Both the read and the write sets are store-owned paths, so the user can
    never reach another store or any admin-only trigger (sync/order-process/
    stock-update/DB recovery/finalize)."""
    if has_unrestricted_scope(current_user):
        return current_user
    path = request.url.path
    if request.method == "GET" and any(p.match(path) for p in _NO_PARAM_READ_PATHS):
        return current_user
    store_name = request.path_params.get("store_name")
    if store_name and _user_owns_store(current_user, store_name):
        if request.method == "GET" and any(p.match(path) for p in _VIEWER_READ_PATHS):
            return current_user
        if request.method in ("PATCH", "POST") and any(p.match(path) for p in _STORE_WRITE_PATHS):
            return current_user
        if request.method == "POST" and _is_purchase_manager(current_user) and any(p.match(path) for p in _PM_WRITE_PATHS):
            return current_user
    raise HTTPException(status_code=403, detail="Legacy Order console is restricted to platform admins.")


def require_admin_or_store_pm(store_name: str, current_user: dict = Depends(get_current_user)) -> dict:
    """Platform admin, or a purchase-manager login assigned to this store."""
    if has_unrestricted_scope(current_user):
        return current_user
    if _is_purchase_manager(current_user) and _user_owns_store(current_user, store_name):
        return current_user
    raise HTTPException(status_code=403, detail="Legacy Order console is restricted to platform admins.")


router = APIRouter(prefix="/api/legacy-order", tags=["Legacy Order"], dependencies=[Depends(require_order_console_access)])


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
def list_stores(active_only: bool = True, current_user: dict = Depends(get_current_user)):
    """Branches from OrderNMC.Stores. Credentials are never returned. A
    non-admin store user gets back only their own store (see
    require_order_console_access), so they can still populate the store
    picker without seeing -- or reaching -- any other branch."""
    try:
        stores = repository.list_stores(active_only)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not has_unrestricted_scope(current_user):
        stores = [s for s in stores if _user_owns_store(current_user, s["store_name"])]
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
def start_order_process(
    payload: OrderProcessRequest, current_user: dict = Depends(get_current_user),
):
    try:
        job_id = service.start_order_process(
            payload.store_name, payload.min_days, payload.max_days, payload.mode,
            confirmed=payload.confirmed,
            confirmed_order_id=payload.confirmed_order_id,
            confirmed_count=payload.confirmed_count,
            confirmed_stale_order=payload.confirmed_stale_order,
            engine=payload.engine,
        )
        return JobStarted(job_id=job_id)
    except service.QtyCheckConfirmationRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except service.StaleCurrentOrder as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        status = 409 if "already running" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc))


# ---- Order engine: legacy SQL or Procurement rule book (both kept) ----

@router.get("/engine/{store_name}")
def get_order_engine(store_name: str):
    try:
        return {"store_name": store_name, "engine": rulebook_order.get_store_engine(store_name),
                "engines": list(rulebook_order.ENGINES), "rulebook_params": rulebook_order.rule_params(store_name)}
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/engine/{store_name}")
def set_order_engine(store_name: str, payload: OrderEngineRequest, current_user: dict = Depends(require_admin)):
    """The store's default engine for Order Process (admin only)."""
    try:
        return rulebook_order.set_store_engine(store_name, payload.engine,
                                               current_user.get("username") or current_user.get("sub"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/engine/{store_name}/compare.xlsx")
def compare_order_engines(store_name: str, current_user: dict = Depends(require_admin)):
    """Dry run: legacy vs rule-book order for the store from the same central
    data, as an Excel workbook. Writes nothing."""
    try:
        store = service._resolve_store(store_name)
        warehouse = service.is_warehouse_store(store_name)
        data = rulebook_order.compare_engines(
            store, warehouse,
            service.WAREHOUSE_MIN_DAYS if warehouse else service.DEFAULT_MIN_DAYS,
            service.WAREHOUSE_MAX_DAYS if warehouse else service.DEFAULT_MAX_DAYS,
            service.WAREHOUSE_RECENCY_DAYS if warehouse else service.DEFAULT_RECENCY_DAYS,
        )
        body = rulebook_order.compare_workbook(data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    name = f"{store_name}_Legacy_vs_RuleBook_{data['as_of']:%Y%m%d_%H%M}.xlsx"
    return Response(content=body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/orders/{store_name}/qty-check-confirmation")
def qty_check_confirmation(store_name: str):
    """Preview for the processing confirmation dialog: how many qtycheck=1/
    status=0 products are pending supplier assignment on the current-date
    order. When count > 1, the client must confirm Order & Process (see
    schemas.OrderProcessRequest.confirmed and service.start_order_process)
    -- this is a warning, not a lock, so there is no token/unlock step here;
    the server simply recomputes the live order_id/count again at
    /order-process time and rejects (409) if either has changed since this
    preview."""
    try:
        order_id, count, sample = repository.qty_check_confirmation_count(store_name)
        return {"order_id": order_id, "count": count, "sample": sample}
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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


@router.get("/orders/{store_name}/workflow")
def order_workflow(store_name: str):
    """Readiness and durable finalization state for the latest generated order."""
    try:
        if not repository.get_store(store_name):
            raise HTTPException(status_code=404, detail="Store not found")
        return repository.order_workflow_summary(store_name)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/orders/{store_name}/header")
def order_header(store_name: str):
    """Order number/date + last GRN number/date for the Order Workspace footer,
    plus the (order_id, updated_at) fingerprint the client uses to detect a
    regenerated order or a line-level change since it last loaded."""
    try:
        if not repository.get_store(store_name):
            raise HTTPException(status_code=404, detail="Store not found")
        return repository.order_header_summary(store_name)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/orders/{store_name}/workflow/audit")
def order_workflow_audit(store_name: str, limit: int = 50):
    try:
        return repository.order_workflow_audit(store_name, limit)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/orders/{store_name}/workflow/finalize")
def finalize_order(
    store_name: str,
    payload: WorkflowActionRequest,
    current_user: dict = Depends(require_admin_or_store_pm),
):
    try:
        return repository.set_order_workflow_finalized(
            store_name, current_user.get("username") or current_user.get("sub"), payload.note
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/orders/{store_name}/workflow/reopen")
def reopen_order(
    store_name: str,
    payload: WorkflowActionRequest,
    current_user: dict = Depends(require_admin_or_store_pm),
):
    try:
        return repository.set_order_workflow_finalized(
            store_name, current_user.get("username") or current_user.get("sub"), payload.note,
            reopen=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/orders/{store_name}/{product_code}")
def update_order_qty(
    store_name: str, product_code: int, payload: UpdateOrderQtyRequest,
    current_user: dict = Depends(get_current_user),
):
    """Manual review edit -- the VB grid's editable OrderQty cell. Setting 0
    marks a product 'no need' without requiring a supplier order."""
    try:
        updated = repository.update_order_qty(
            store_name, product_code, payload.order_qty,
            current_user.get("username") or current_user.get("sub"),
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Order row not found")
        return {"store_name": store_name, "product_code": product_code, "order_qty": payload.order_qty}
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---- Supplier-assignment ordering workflow (Purchase-Manager-style grid) ----

@router.get("/suppliers/{store_name}")
def list_suppliers(store_name: str, search: str = ""):
    """Supplier search list for a store (VB dgvSupplierList)."""
    try:
        return repository.list_suppliers(store_name, search)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/orders/{store_name}/by-supplier")
def orders_by_supplier(store_name: str, supplier_code: str, mode: str = "history"):
    """Orderable rows for a supplier -- mode='history' (purchase history) or
    mode='stock' (live SupplierStock match, with stock/rack columns)."""
    try:
        return repository.orders_by_supplier(store_name, supplier_code, mode)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/orders/{store_name}/all-open")
def all_open_orderables(store_name: str):
    """Every still-open orderable product for the store, independent of any
    supplier match -- the By Supplier grid's "Load all products" toggle. The
    operator assigns/exports these to whichever supplier is picked."""
    try:
        return repository.all_open_orderables(store_name)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/orders/{store_name}/by-supplier/export-count")
def orders_by_supplier_export_count(store_name: str, supplier_code: str):
    """Stock-mode exportable row count for this store/supplier -- exactly the
    eligibility Export always acts on, regardless of which History/Live Stock
    tab the grid is currently showing. Powers the Export button's label/count
    without loading the full stock grid just to count it."""
    try:
        return {"count": repository.orders_by_supplier_export_count(store_name, supplier_code)}
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/orders/{store_name}/assigned")
def assigned_orders(store_name: str, supplier_code: str):
    """Rows already assigned to a supplier (status=1)."""
    try:
        return repository.assigned_orders(store_name, supplier_code)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/orders/{store_name}/assigned/all")
def all_assigned_orders(store_name: str):
    """Every assigned row for the store across ALL suppliers at once --
    Supplier Order Details' "All Suppliers" view."""
    try:
        return repository.all_assigned_orders(store_name)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/orders/{store_name}/unavailable/remove")
def remove_unavailable_from_supplier(
    store_name: str, payload: SupplierCodeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Bulk-drop every currently-Assigned line for this supplier where the
    supplier's own live stock (SupplierStock.Stock) is <= 0 or unmatched --
    back to status=0, qtycheck=1, no supplier -- so another supplier can
    pick them up. See repository.remove_unavailable_from_supplier."""
    try:
        removed = repository.remove_unavailable_from_supplier(
            store_name, payload.supplier_code,
            current_user.get("username") or current_user.get("sub"),
        )
        return {"removed_product_codes": removed, "removed_count": len(removed)}
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/orders/{store_name}/auto-assign")
def auto_assign_preview(store_name: str):
    """Bulk Assign · Best Margin preview: proposed supplier per Pending Order
    line (see repository.auto_assign_proposals)."""
    try:
        return repository.auto_assign_proposals(store_name)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/orders/{store_name}/auto-assign")
def auto_assign_apply(
    store_name: str, payload: AutoAssignRequest,
    current_user: dict = Depends(get_current_user),
):
    """Assign the best-margin proposals (recomputed server-side)."""
    try:
        return repository.auto_assign_apply(
            store_name, payload.product_codes,
            current_user.get("username") or current_user.get("sub"),
        )
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/orders/{store_name}/{product_code}/assign")
def assign_supplier(
    store_name: str, product_code: int, payload: AssignSupplierRequest,
    current_user: dict = Depends(get_current_user),
):
    """Assign/unassign a supplier to an order line (VB status 0<->1 toggle)."""
    try:
        result = repository.assign_supplier(
            store_name, product_code, payload.supplier_code, payload.supplier_name,
            current_user.get("username") or current_user.get("sub"),
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Order row not found")
        return result
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/orders/{store_name}/export")
def export_order(
    store_name: str, payload: ExportOrderRequest,
    current_user: dict = Depends(get_current_user),
):
    """Build and return the Order Workspace Excel export (or a .zip of parts
    when split_size splits the file).

    From the By Supplier grid the request carries product_codes -- the exact
    rows left in the grid after the operator's deletions. Export assigns only
    those to the supplier (status=1) and includes only those, so a deleted row
    is neither assigned nor exported. From the Assigned view product_codes is
    omitted and export simply reflects whatever is already assigned. See
    order_export.export_order."""
    try:
        if not repository.get_store(store_name):
            raise HTTPException(status_code=404, detail="Store not found")
        result = order_export.export_order(
            store_name, payload.supplier_code, payload.supplier_name,
            payload.mode, payload.split_size,
            current_user.get("username") or current_user.get("sub"),
            columns=payload.columns, file_format=payload.file_format, order_no=payload.order_no,
            product_codes=payload.product_codes, all_products=payload.all_products,
            images=payload.images,
        )
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except order_export.NoExportableRows as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except order_export.ExportGenerationFailed as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={
            "Content-Disposition": _header_value(f'attachment; filename="{result.filename}"'),
            "X-Exported-Count": str(result.count),
            "X-Supplier-Name": _header_value(result.supplier_name),
            "Access-Control-Expose-Headers": "Content-Disposition, X-Exported-Count, X-Supplier-Name",
        },
    )


@router.post("/orders/{store_name}/export-pending")
def export_pending_order(
    store_name: str, payload: ExportPendingOrderRequest,
    current_user: dict = Depends(get_current_user),
):
    """Export the Pending grid (qtycheck=1, status=0 -- reviewed, no supplier
    yet) to Excel/CSV. Read-only: unlike export_order, nothing is assigned
    here -- Pending rows stay status=0. See order_export.export_pending_order."""
    try:
        if not repository.get_store(store_name):
            raise HTTPException(status_code=404, detail="Store not found")
        result = order_export.export_pending_order(
            store_name, payload.split_size,
            columns=payload.columns, file_format=payload.file_format, order_no=payload.order_no,
            images=payload.images,
        )
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except order_export.NoExportableRows as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except order_export.ExportGenerationFailed as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={
            "Content-Disposition": _header_value(f'attachment; filename="{result.filename}"'),
            "X-Exported-Count": str(result.count),
            "Access-Control-Expose-Headers": "Content-Disposition, X-Exported-Count",
        },
    )


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


# ---- Restore by OrderId -- admin-only recovery workflow (see repository.
# restore_backup_order for the full safety contract: same store-applock as
# the processing lock, all-or-nothing, per-row audit trail). ----

@router.get("/orders/{store_name}/restorable/{order_id}")
def restorable_order_preview(
    store_name: str, order_id: int, current_user: dict = Depends(require_admin),
):
    """Preview for the restore confirmation screen: backup timestamp,
    product count, suppliers represented. 404 if that (store, order_id)
    combination has no backup at all."""
    try:
        preview = repository.restorable_order_preview(store_name, order_id)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if preview is None:
        raise HTTPException(
            status_code=404,
            detail=f"No backup exists for '{store_name}' order #{order_id}.",
        )
    return preview


@router.post("/orders/{store_name}/restore")
def restore_backup_order(
    store_name: str, payload: RestoreBackupOrderRequest,
    current_user: dict = Depends(require_admin),
):
    """Restore a specific, explicitly-selected backup order's rows back onto
    the current order -- admin-only, all-or-nothing (see repository.
    restore_backup_order). 409 on any validation failure (missing backup,
    products with no matching live row) -- nothing is partially restored."""
    try:
        return repository.restore_backup_order(
            store_name, payload.order_id,
            current_user.get("username") or current_user.get("sub"),
        )
    except repository.PendingExportBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except repository.RestoreValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---- Qty Check screen (port of Form1's "Qty Check" process) ----

@router.get("/qty-check/{store_name}")
def qty_check_rows(store_name: str):
    try:
        return repository.qty_check_rows(store_name)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/qty-check/{store_name}/reset-pending")
def reset_pending_qty_check(store_name: str, current_user: dict = Depends(require_admin)):
    try:
        return repository.reset_pending_qty_check(
            store_name, current_user.get("username") or current_user.get("sub"),
        )
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ---- Pending Order screen (port of Form1's "Pending Order" process:
# reviewed lines, qtycheck = 1, not yet assigned to a supplier, status = 0) ----

@router.get("/pending-order/{store_name}")
def pending_order_rows(store_name: str):
    try:
        return repository.pending_order_rows(store_name)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/qty-check/{store_name}/{product_code}")
def update_qty_check(
    store_name: str, product_code: int, payload: UpdateQtyCheckRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        result = repository.update_qty_check(
            store_name, product_code, payload.order_qty,
            current_user.get("username") or current_user.get("sub"),
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Order row not found")
        return result
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/qty-check/{store_name}/{product_code}/skip")
def skip_product(
    store_name: str, product_code: int, payload: SkipProductRequest,
    current_user: dict = Depends(get_current_user),
):
    """Skip a line with one of the platform's skip modes (see
    repository.skip_product): it goes to Rejected with Or Qty 0, and the two
    persistent modes carry into future orders until the product sells."""
    try:
        result = repository.skip_product(
            store_name, product_code, payload.mode,
            current_user.get("username") or current_user.get("sub"),
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Open order row not found")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/orders/{store_name}/{product_code}/remarks")
def update_remarks(
    store_name: str, product_code: int, payload: UpdateRemarksRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        result = repository.update_remarks(
            store_name, product_code, payload.remarks,
            current_user.get("username") or current_user.get("sub"),
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Order row not found")
        return result
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/qty-check/{store_name}/purchase-invoice")
def purchase_invoice_lines(store_name: str, grn_no: int, series: str = "", grn_date: str = "", supplier_code: str | None = None):
    """All lines of one purchase invoice / GRN (see repository.purchase_invoice_lines)."""
    try:
        if not repository.get_store(store_name):
            raise HTTPException(status_code=404, detail="Store not found")
        if not grn_date:
            raise HTTPException(status_code=400, detail="grn_date is required (GRN numbers repeat across years).")
        return repository.purchase_invoice_lines(store_name, grn_no, series, grn_date[:10], supplier_code)
    except database.LegacyDatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/qty-check/{store_name}/sale-bill")
def sale_bill_lines(store_name: str, bnumber: str, bill_date: str = ""):
    """All lines + header of one sales bill (see repository.sale_bill_lines)."""
    try:
        if not repository.get_store(store_name):
            raise HTTPException(status_code=404, detail="Store not found")
        if not bill_date:
            raise HTTPException(status_code=400, detail="bill_date is required (bill numbers repeat across years).")
        return repository.sale_bill_lines(store_name, bnumber, bill_date[:10])
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
