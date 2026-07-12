"""Pydantic request schemas for Purchase Manager operations (Sprint 2)."""

from typing import List, Optional

from pydantic import BaseModel, Field


# --- Workspace review (Modules 2-3) ---------------------------------------

class FinalQtyUpdate(BaseModel):
    final_qty: float = Field(..., ge=0)
    override_reason: Optional[str] = Field(None, max_length=300)
    reviewed_by: Optional[str] = None


class SkipRequest(BaseModel):
    skip_reason: str = Field(..., min_length=1, max_length=300)
    reviewed_by: Optional[str] = None


class ReviewedBy(BaseModel):
    reviewed_by: Optional[str] = None


# --- Supplier assignment (Module 5) ---------------------------------------

class AssignRequest(BaseModel):
    supplier_code: str = Field(..., min_length=1, max_length=100)
    qty: float = Field(..., gt=0)
    remarks: Optional[str] = Field(None, max_length=300)
    created_by: Optional[str] = None


class BulkAssignItem(BaseModel):
    order_item_id: str
    qty: Optional[float] = Field(None, gt=0)
    remarks: Optional[str] = Field(None, max_length=300)


class BulkAssignRequest(BaseModel):
    supplier_code: str = Field(..., min_length=1, max_length=100)
    items: List[BulkAssignItem]
    created_by: Optional[str] = None


class ChangeSupplierRequest(BaseModel):
    supplier_code: str = Field(..., min_length=1, max_length=100)
    updated_by: Optional[str] = None


# --- Export (Module 6) -----------------------------------------------------

class ExportRequest(BaseModel):
    exported_by: str = Field(..., min_length=1)
    assignment_ids: Optional[List[str]] = None
    # Export every current, live (draft) assignment for one supplier, resolved
    # fresh from the DB at request time — used by the plain per-supplier Export
    # button so it can never miss an assignment made after the last client
    # reload (§14). Ignored when assignment_ids is given (that path already
    # reflects an explicit client-side selection, e.g. Export-Qty hold-backs).
    supplier_code: Optional[str] = None


# --- GRN + Pending + Cycle close (Sprint 3) -------------------------------

class GrnSubmit(BaseModel):
    last_grn_number: str = Field(..., min_length=1, max_length=50)
    submitted_by: Optional[str] = None


class PendingAdjust(BaseModel):
    remaining_qty: float = Field(..., ge=0)
    reviewed_by: Optional[str] = None


class ManualAdd(BaseModel):
    product_code: str = Field(..., min_length=1, max_length=100)
    product_name: Optional[str] = Field(None, max_length=300)
    qty: float = Field(..., gt=0)
    created_by: Optional[str] = None


class CycleClose(BaseModel):
    # End GRN / End Sale Bill are read from synced data on close (no manual
    # entry), so they are not accepted here. `force` = the user confirmed closing
    # while pending items still exist (clear them, do not carry forward).
    closed_by: Optional[str] = None
    force: bool = False


class PendingBulk(BaseModel):
    action: str = Field(..., pattern="^(carry|skip|finalize)$")
    order_item_ids: List[str] = Field(..., min_length=1)
    reviewed_by: Optional[str] = None


class PipelineRun(BaseModel):
    tenant_id: str
    store_id: str
    rolling_days: int = 90
    min_days: float = 13
    max_days: float = 18
    created_by: Optional[str] = None


# --- Supplier Auto Assign settings -----------------------------------------

class SupplierSettingsUpdate(BaseModel):
    auto_assign: Optional[bool] = None
    min_products: Optional[int] = Field(None, ge=1)
    export_rank: Optional[int] = Field(None, ge=0)
