"""HTTP routing for Purchase Manager operations (Sprint 2).

Mounted onto the module's main `router` (/api/procurement). Covers Workspace,
Supplier Queue, Supplier Assignment (single/bulk/change/remove) and Export.
"""

import json
from typing import Optional

from fastapi import APIRouter, File, Form, Query, UploadFile

from modules.procurement import workspace_service
from modules.procurement import supplier_service
from modules.procurement import supplier_stock_service
from modules.procurement import assignment_service
from modules.procurement import export_service
from modules.procurement import export_document_service
from modules.procurement import supplier_reply_service
from modules.procurement import reconciliation_service
from modules.procurement import reconciliation_repository
from modules.procurement import pending_service
from modules.procurement.pm_schemas import (
    FinalQtyUpdate, SkipRequest, ReviewedBy,
    AssignRequest, BulkAssignRequest, ChangeSupplierRequest, ExportRequest,
    ExportDocumentRequest, SupplierReplyImportRequest,
    GrnSubmit, PendingAdjust, ManualAdd, PendingBulk, SupplierSettingsUpdate,
    SupplierExportSettingsUpdate,
)

router = APIRouter(tags=["Procurement Purchase Manager"])


# --------------------------------------------------------------------------
# Workspace
# --------------------------------------------------------------------------

@router.get("/refreshes/{refresh_id}/workspace")
def workspace(
    refresh_id: str,
    tenant_id: str = Query(...),
    search: Optional[str] = Query(None),
    item_status: Optional[str] = Query(None),
    movement_class: Optional[str] = Query(None),
    stock_status: Optional[str] = Query(None),
    # Comma-separated subset of pending|finalized|assigned|skipped — the grid's
    # Planning State checkboxes. Was applied client-side over every already-
    # downloaded row; now a real server filter (see _PLANNING_STATE_CASE).
    planning_state: Optional[str] = Query(None),
    product_type: Optional[str] = Query(None),
    is_manual: Optional[bool] = Query(None),
    sort_by: str = Query("product_code"),
    sort_dir: str = Query("asc"),
    page: int = Query(1, ge=1),
    # A cycle's whole VPL is loaded at once (700–2000+ rows) — the grid scrolls
    # internally. Raised from 500 so the workspace never truncates; true row
    # virtualization is the follow-up for very large cycles.
    page_size: int = Query(50, ge=1, le=5000),
):
    filters = {
        "search": search, "item_status": item_status,
        "movement_class": movement_class, "stock_status": stock_status,
        "planning_state": [s for s in planning_state.split(",") if s] if planning_state else None,
        "product_type": product_type,
        "is_manual": is_manual,
    }
    return workspace_service.list_workspace(
        tenant_id, refresh_id, filters, sort_by, sort_dir, page, page_size
    )


@router.get("/refreshes/{refresh_id}/workspace/summary")
def workspace_summary(
    refresh_id: str,
    tenant_id: str = Query(...),
    search: Optional[str] = Query(None),
    movement_class: Optional[str] = Query(None),
):
    """Footer counts (Total Products / Pending Review / Assigned / Finalized /
    Skipped) for the whole refresh, computed in SQL. Scope matches the grid's
    base load (search + movement_class only) — Planning State / Product Type /
    Manual are display filters and never narrowed these totals. Purchase Value
    is not included — see workspace_repository.get_summary's docstring."""
    filters = {"search": search, "movement_class": movement_class}
    return workspace_service.get_summary(tenant_id, refresh_id, filters)


@router.get("/order-items/{order_item_id}")
def get_order_item(order_item_id: str, tenant_id: str = Query(...)):
    return workspace_service.get_item(tenant_id, order_item_id)


@router.put("/order-items/{order_item_id}/final-qty")
def set_final_qty(
    order_item_id: str, payload: FinalQtyUpdate, tenant_id: str = Query(...)
):
    return workspace_service.set_final_qty(
        tenant_id, order_item_id, payload.final_qty,
        payload.override_reason, payload.reviewed_by,
    )


@router.post("/order-items/{order_item_id}/restore-suggested")
def restore_suggested(
    order_item_id: str, payload: ReviewedBy, tenant_id: str = Query(...)
):
    return workspace_service.restore_suggested(
        tenant_id, order_item_id, payload.reviewed_by
    )


@router.post("/order-items/{order_item_id}/skip")
def skip(order_item_id: str, payload: SkipRequest, tenant_id: str = Query(...)):
    return workspace_service.skip_item(
        tenant_id, order_item_id, payload.skip_reason, payload.reviewed_by
    )


@router.post("/order-items/{order_item_id}/restore")
def restore(order_item_id: str, payload: ReviewedBy, tenant_id: str = Query(...)):
    return workspace_service.restore_item(
        tenant_id, order_item_id, payload.reviewed_by
    )


@router.post("/order-items/{order_item_id}/defer")
def defer(order_item_id: str, payload: ReviewedBy, tenant_id: str = Query(...)):
    """Assignment Deferred (Space Bar) — excludes the row from Auto/Bulk
    Assignment while keeping its Final Qty. Un-defer reuses POST .../restore."""
    return workspace_service.defer_item(
        tenant_id, order_item_id, payload.reviewed_by
    )


# --------------------------------------------------------------------------
# Supplier Queue
# --------------------------------------------------------------------------

@router.get("/order-items/{order_item_id}/supplier-queue")
def supplier_queue(
    order_item_id: str,
    tenant_id: str = Query(...),
    limit: int = Query(3, ge=1, le=50),
):
    return supplier_service.get_queue(tenant_id, order_item_id, limit)


@router.get("/refreshes/{refresh_id}/supplier-recommendations")
def supplier_recommendations(
    refresh_id: str,
    tenant_id: str = Query(...),
    limit: int = Query(5, ge=1, le=10),
):
    """Top-N supplier recommendations for every working item in the Refresh
    (batched — one round-trip). Read-only; same ranking as the per-item queue."""
    return supplier_service.get_queue_bulk(tenant_id, refresh_id, limit)


@router.get("/refreshes/{refresh_id}/supplier-products")
def supplier_products(
    refresh_id: str,
    tenant_id: str = Query(...),
    supplier_code: str = Query(...),
):
    """Order-item ids the given supplier has purchase history for (Supplier
    Purchasing mode shows exactly these products)."""
    return supplier_service.products_for_supplier(tenant_id, refresh_id, supplier_code)


@router.get("/suppliers/search")
def supplier_search(
    tenant_id: str = Query(...),
    q: str = Query("", alias="q"),
    store_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    return supplier_service.search(tenant_id, store_id, q, limit)


@router.get("/suppliers/{supplier_code}/stats")
def supplier_stats(
    supplier_code: str,
    tenant_id: str = Query(...),
    store_id: Optional[str] = Query(None),
):
    return supplier_service.stats(tenant_id, supplier_code, store_id)


@router.get("/suppliers/settings")
def supplier_settings(tenant_id: str = Query(...), store_id: str = Query(...)):
    """Every store supplier's Auto Assign settings (auto_assign, min_products,
    export_rank) — the Supplier Rank & Settings panel narrows this to
    suppliers relevant to the open refresh client-side."""
    return supplier_service.list_settings(tenant_id, store_id)


@router.put("/suppliers/{supplier_code}/settings")
def update_supplier_settings(
    supplier_code: str,
    body: SupplierSettingsUpdate,
    tenant_id: str = Query(...),
    store_id: str = Query(...),
):
    return supplier_service.update_settings(
        tenant_id, store_id, supplier_code,
        auto_assign=body.auto_assign, min_products=body.min_products, export_rank=body.export_rank,
    )


@router.get("/suppliers/{supplier_code}/export-settings")
def supplier_export_settings(
    supplier_code: str, tenant_id: str = Query(...), store_id: str = Query(...),
):
    """This supplier's remembered Export Document choices (format, columns,
    Order Qty header, sort, desktop export folder) — defaults when they've
    never exported for this supplier before."""
    return supplier_service.get_export_settings(tenant_id, store_id, supplier_code)


@router.put("/suppliers/{supplier_code}/export-settings")
def update_supplier_export_settings(
    supplier_code: str,
    body: SupplierExportSettingsUpdate,
    tenant_id: str = Query(...),
    store_id: str = Query(...),
):
    return supplier_service.save_export_settings(
        tenant_id, store_id, supplier_code,
        body.format, body.columns, body.order_qty_header, body.sort_by, body.export_folder_path,
    )


# --------------------------------------------------------------------------
# Supplier Live Stock (read-only: supplier_stock ∩ SupplierProductMatch ∩ VPL)
# --------------------------------------------------------------------------

@router.get("/refreshes/{refresh_id}/supplier-stock")
def supplier_stock(
    refresh_id: str,
    tenant_id: str = Query(...),
    supplier_code: str = Query(...),
    search: Optional[str] = Query(None),
    only_available: bool = Query(True),
):
    return supplier_stock_service.list_supplier_stock(
        tenant_id, refresh_id, supplier_code, search, only_available
    )


@router.get("/refreshes/{refresh_id}/products-with-offers")
def products_with_offers(refresh_id: str, tenant_id: str = Query(...)):
    """Product codes in this refresh's VPL that carry an offer — free qty or a
    discount % on the product's last purchase (sync.PurchaseTrans), or a live
    supplier scheme. Powers "Has Offer" in Review All / Supplier Purchasing."""
    return supplier_stock_service.products_with_offers(tenant_id, refresh_id)


@router.get("/supplier-stock/mapping")
def supplier_stock_mapping(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    supplier_code: str = Query(...),
):
    """Saved Excel header map for a supplier+store + the canonical targets."""
    return supplier_stock_service.get_mapping(tenant_id, store_id, supplier_code)


@router.post("/supplier-stock/preview")
async def supplier_stock_preview(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    supplier_code: str = Query(...),
    file: UploadFile = File(...),
):
    """Parse an uploaded stock file: detected headers, sample rows, suggested map."""
    data = await file.read()
    return supplier_stock_service.preview_import(
        tenant_id, store_id, supplier_code, data, file.filename
    )


@router.post("/supplier-stock/import")
async def supplier_stock_import(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    supplier_code: str = Query(...),
    created_by: Optional[str] = Query(None),
    file: UploadFile = File(...),
    mapping: str = Form(...),
):
    """Normalize + REPLACE the supplier's live stock for the store from the upload.
    ``mapping`` is a JSON object {excel_header: canonical_column}."""
    data = await file.read()
    return supplier_stock_service.run_import(
        tenant_id, store_id, supplier_code, data, file.filename,
        json.loads(mapping), created_by,
    )


# --------------------------------------------------------------------------
# Supplier Assignment
# --------------------------------------------------------------------------

@router.get("/order-items/{order_item_id}/assignments")
def list_assignments(order_item_id: str, tenant_id: str = Query(...)):
    return assignment_service.list_for_item(tenant_id, order_item_id)


@router.get("/refreshes/{refresh_id}/assignments")
def list_refresh_assignments(refresh_id: str, tenant_id: str = Query(...)):
    """Every live assignment for the whole Refresh in one round-trip — powers
    the Supplier Queue build (was one /assignments request per assigned item)."""
    return assignment_service.list_for_refresh(tenant_id, refresh_id)


@router.post("/order-items/{order_item_id}/assignments")
def assign(order_item_id: str, payload: AssignRequest, tenant_id: str = Query(...)):
    return assignment_service.assign_single(
        tenant_id, order_item_id, payload.supplier_code,
        payload.qty, payload.remarks, payload.created_by,
    )


@router.post("/assignments/bulk")
def bulk_assign(payload: BulkAssignRequest, tenant_id: str = Query(...)):
    return assignment_service.assign_bulk(
        tenant_id, payload.supplier_code,
        [i.dict() for i in payload.items], payload.created_by,
    )


@router.put("/assignments/{assignment_id}/supplier")
def change_supplier(
    assignment_id: str, payload: ChangeSupplierRequest, tenant_id: str = Query(...)
):
    return assignment_service.change_supplier(
        tenant_id, assignment_id, payload.supplier_code, payload.updated_by
    )


@router.delete("/assignments/{assignment_id}")
def remove_assignment(
    assignment_id: str,
    tenant_id: str = Query(...),
    deleted_by: Optional[str] = Query(None),
):
    return assignment_service.remove_assignment(tenant_id, assignment_id, deleted_by)


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------

@router.post("/refreshes/{refresh_id}/export")
def export(refresh_id: str, payload: ExportRequest, tenant_id: str = Query(...)):
    return export_service.export_refresh(
        tenant_id, refresh_id, payload.exported_by,
        payload.assignment_ids, payload.supplier_code,
    )


@router.post("/refreshes/{refresh_id}/export-document")
def export_document(
    refresh_id: str, payload: ExportDocumentRequest, tenant_id: str = Query(...)
):
    """Configurable Export Document — Excel (default, supplier-editable
    Status/Available Qty + hidden assignment_id for round-trip), PDF, or
    Image. refresh_id is accepted for URL/route symmetry with the rest of
    this module but the lines are resolved directly by assignment_id."""
    from fastapi.responses import Response

    content, filename, media_type = export_document_service.build_document(
        tenant_id,
        [i.dict() for i in payload.items],
        payload.format,
        payload.columns,
        payload.order_qty_header,
        payload.sort_by,
        payload.supplier_code,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/refreshes/{refresh_id}/supplier-reply/preview")
async def supplier_reply_preview(
    refresh_id: str,
    tenant_id: str = Query(...),
    file: UploadFile = File(...),
):
    """Parse the supplier's returned Excel: matched rows + warnings, before
    anything is written. refresh_id kept for route symmetry — rows are
    matched directly by the hidden Assignment ID column."""
    data = await file.read()
    return supplier_reply_service.preview_reply_import(tenant_id, data, file.filename)


@router.post("/refreshes/{refresh_id}/supplier-reply/import")
def supplier_reply_import(
    refresh_id: str,
    payload: SupplierReplyImportRequest,
    tenant_id: str = Query(...),
):
    """Apply a confirmed Supplier Reply preview: Available/Partial/Not
    Available per line, rolling any shortfall into the existing Pending tab
    and recording it for next-cycle supplier exclusion at cycle close."""
    return supplier_reply_service.apply_reply_import(
        tenant_id, [r.dict() for r in payload.rows], payload.imported_by,
    )


@router.get("/refreshes/{refresh_id}/export-history")
def export_history(refresh_id: str, tenant_id: str = Query(...)):
    return export_service.history(tenant_id, refresh_id)


@router.get("/exports/{batch_no}")
def export_detail(batch_no: str, tenant_id: str = Query(...)):
    return export_service.batch_detail(tenant_id, batch_no)


# --------------------------------------------------------------------------
# GRN completion + reconciliation (Modules 1-2)
# --------------------------------------------------------------------------

@router.post("/refreshes/{refresh_id}/grn")
def submit_grn(refresh_id: str, payload: GrnSubmit, tenant_id: str = Query(...)):
    return reconciliation_service.submit_grn(
        tenant_id, refresh_id, payload.last_grn_number, payload.submitted_by
    )


# --------------------------------------------------------------------------
# Pending management (Module 3)
# --------------------------------------------------------------------------

@router.get("/refreshes/{refresh_id}/pending")
def list_pending(
    refresh_id: str,
    tenant_id: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
):
    return pending_service.list_pending(tenant_id, refresh_id, page, page_size)


@router.put("/order-items/{order_item_id}/pending")
def adjust_pending(
    order_item_id: str, payload: PendingAdjust, tenant_id: str = Query(...)
):
    return pending_service.adjust(
        tenant_id, order_item_id, payload.remaining_qty, payload.reviewed_by
    )


@router.post("/order-items/{order_item_id}/pending/skip")
def skip_pending(order_item_id: str, payload: ReviewedBy, tenant_id: str = Query(...)):
    return pending_service.skip(tenant_id, order_item_id, payload.reviewed_by)


@router.post("/order-items/{order_item_id}/pending/carry-forward")
def carry_forward(order_item_id: str, payload: ReviewedBy, tenant_id: str = Query(...)):
    return pending_service.carry_forward(tenant_id, order_item_id, payload.reviewed_by)


@router.post("/refreshes/{refresh_id}/pending/finalize")
def finalize_pending(refresh_id: str, payload: ReviewedBy, tenant_id: str = Query(...)):
    return pending_service.finalize(tenant_id, refresh_id, payload.reviewed_by)


@router.post("/refreshes/{refresh_id}/pending/bulk")
def bulk_pending(refresh_id: str, payload: PendingBulk, tenant_id: str = Query(...)):
    """Bulk pending action (carry / skip / finalize) over many items — powers
    bulk processing and supplier-wise carry."""
    return pending_service.bulk(
        tenant_id, refresh_id, payload.action,
        payload.order_item_ids, payload.reviewed_by,
    )


@router.get("/refreshes/{refresh_id}/pending/report")
def pending_report(refresh_id: str, tenant_id: str = Query(...)):
    """Server-generated pending report (.xlsx download)."""
    from fastapi.responses import Response

    content, filename = pending_service.report_xlsx(tenant_id, refresh_id)
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/refreshes/{refresh_id}/manual-items")
def add_manual_item(refresh_id: str, payload: ManualAdd, tenant_id: str = Query(...)):
    from fastapi import HTTPException
    refresh = reconciliation_repository.get_refresh(tenant_id, refresh_id)
    if not refresh:
        raise HTTPException(status_code=404, detail="Refresh not found")
    return pending_service.add_manual(
        tenant_id, refresh_id, refresh["cycle_id"], refresh.get("store_id"),
        payload.product_code, payload.product_name, payload.qty, payload.created_by,
    )


# --------------------------------------------------------------------------
# Decision Explorer (Module 6)
# --------------------------------------------------------------------------

@router.get("/order-items/{order_item_id}/decision")
def decision(order_item_id: str, tenant_id: str = Query(...)):
    return workspace_service.get_decision(tenant_id, order_item_id)
