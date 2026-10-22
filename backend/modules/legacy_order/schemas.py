from typing import List, Optional

from pydantic import BaseModel


class SyncRequest(BaseModel):
    store_name: str
    tables: Optional[List[str]] = None  # None = the full legacy table plan


class OrderProcessRequest(BaseModel):
    store_name: str
    min_days: Optional[int] = None  # Nexora defaults: 13 / 18
    max_days: Optional[int] = None
    mode: str = "local"  # 'local' = OrderNMC's synced copy, 'remote' = branch DB
    # Pending-supplier-assignment WARNING (see repository.
    # qty_check_confirmation_count / service.QtyCheckConfirmationRequired):
    # when more than one qty_check=1/status=0 product exists on the
    # current-date order, the server rejects (409) unless confirmed is True
    # AND confirmed_order_id/confirmed_count still match the live
    # order_id/count -- a stale dialog (state changed since it opened) must
    # re-fetch the preview and reconfirm, not silently reuse an old count.
    # This is an ordinary warning acknowledgement, not a privileged action --
    # any authenticated caller may confirm it.
    confirmed: bool = False
    confirmed_order_id: Optional[int] = None
    confirmed_count: Optional[int] = None


class RestoreBackupOrderRequest(BaseModel):
    # Always the operator's explicit selection -- never inferred as
    # MAX(OrderId) (see repository.restore_backup_order's docstring and
    # Requirement D: "Never infer the source snapshot from MAX(OrderId)
    # when the user explicitly selected an OrderId").
    order_id: int


class StockUpdateRequest(BaseModel):
    store_name: str
    source_store_name: str = "NMW"


class JobStarted(BaseModel):
    job_id: str


class ComparePreviousOrderRequest(BaseModel):
    store_name: str
    order_id: int


class CompareSupplierRequest(ComparePreviousOrderRequest):
    supplier_code: str


class UpdateOrderQtyRequest(BaseModel):
    order_qty: int


class UpdateQtyCheckRequest(BaseModel):
    order_qty: int


class UpdateRemarksRequest(BaseModel):
    remarks: str = ""


class WorkflowActionRequest(BaseModel):
    note: Optional[str] = None


class AssignSupplierRequest(BaseModel):
    supplier_code: str
    supplier_name: str


class SupplierCodeRequest(BaseModel):
    supplier_code: str


class ExportOrderRequest(BaseModel):
    supplier_code: str
    supplier_name: str
    mode: str = "history"  # matches the By-Supplier view's History/Live Stock toggle
    split_size: int = 0  # 0 = single file; >0 splits into "Part N of M" chunks (zipped)
    # Optional column selection — omit (None) to keep the legacy fixed
    # layout exactly as before. When provided, must include at least
    # product_code/product_name/order_qty (enforced client-side; the
    # server just drops any column key it doesn't recognize).
    columns: list[str] | None = None
    file_format: str = "xls"  # 'xlsx' | 'xls' | 'csv' -- owner default (2026-10-22): 'xls'
    order_no: str | None = None  # current order header's order_id, for the standard filename
    # Explicit set of product codes the operator curated in the By Supplier
    # grid (after any row deletions). When provided, export assigns exactly
    # these to the supplier and exports only them -- so a deleted row is
    # neither assigned nor exported. Omit (None) from the Assigned view, where
    # export just reflects what's already assigned.
    product_codes: list[str] | None = None
    # "Load all products" mode: the grid loaded every open orderable product
    # (not just this supplier's history/stock match), so the server re-resolves
    # the curated codes against the all-open set instead of the supplier match
    # -- otherwise a deliberately-added, unmatched product would be dropped.
    all_products: bool = False
    # Hard exclusion list: every product code the operator pressed Delete/✕ on
    # THIS session (App.jsx's removedCodes, client-side only, never persisted
    # to the DB). product_codes already omits these (filteredRows already
    # drops removedCodes before building it), so in the normal case this is
    # redundant with product_codes -- it exists as a second, independent
    # guard: if product_codes is ever stale (e.g. a reload race re-adds a
    # product the operator already deleted before Export was clicked),
    # removed_product_codes still wins and the product is excluded from BOTH
    # assignment and export, never just from the display. See
    # order_export.export_order.
    removed_product_codes: list[str] | None = None


class ExportPendingOrderRequest(BaseModel):
    # No supplier_code/supplier_name -- the Pending grid (qtycheck=1,
    # status=0) has no supplier yet by definition; export here is read-only,
    # never an assignment step (see order_export.export_pending_order).
    split_size: int = 0
    columns: list[str] | None = None
    file_format: str = "xls"  # owner default (2026-10-22): 'xls'
    order_no: str | None = None


class EmergencyRepairRequest(BaseModel):
    # Guard rail: the destructive REPAIR_ALLOW_DATA_LOSS path only runs when the
    # caller explicitly opts in. The UI sends this from a confirmation dialog.
    confirm: bool = False
