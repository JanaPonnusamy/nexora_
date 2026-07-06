"""Pydantic schemas for the Virtual Product List (VPL) — Sprint 2.

Models product identity and snapshot metadata only. No calculated fields,
order quantities, supplier, stock, pending, shortage or expiry data.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

VPL_STATUSES = ("Draft", "Refreshing", "Ready", "Archived")


# --------------------------------------------------------------------------
# VPL header
# --------------------------------------------------------------------------

class VplCreate(BaseModel):
    tenant_id: str
    cycle_id: str
    store_id: Optional[str] = None
    snapshot_name: str = Field(..., min_length=1, max_length=200)
    # immutable snapshot parameters (every Refresh is reproducible)
    rolling_days: Optional[int] = None
    min_days: Optional[float] = None
    max_days: Optional[float] = None
    previous_refresh_id: Optional[str] = None
    snapshot_grn_number: Optional[str] = Field(None, max_length=50)
    snapshot_sale_bill_number: Optional[str] = Field(None, max_length=50)
    sync_execution_id: Optional[str] = None
    created_by: Optional[str] = None  # user_id (UNIQUEIDENTIFIER)


class VplOut(BaseModel):
    refresh_id: str
    tenant_id: str
    cycle_id: str
    store_id: Optional[str] = None
    snapshot_name: str
    snapshot_status: str
    refresh_no: Optional[int] = None
    rolling_days: Optional[int] = None
    min_days: Optional[float] = None
    max_days: Optional[float] = None
    previous_refresh_id: Optional[str] = None
    snapshot_grn_number: Optional[str] = None
    snapshot_sale_bill_number: Optional[str] = None
    sync_execution_id: Optional[str] = None
    generated_product_count: Optional[int] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None


# --------------------------------------------------------------------------
# VPL product
# --------------------------------------------------------------------------

class VpProductAdd(BaseModel):
    product_id: str
    product_code: Optional[str] = Field(None, max_length=100)
    product_name: Optional[str] = Field(None, max_length=300)
    manufacturer_id: Optional[str] = None
    category_id: Optional[str] = None
    schedule_type: Optional[str] = Field(None, max_length=50)
    unit: Optional[str] = Field(None, max_length=50)
    is_active: bool = True
    snapshot_version: int = 1


class VpProductOut(BaseModel):
    virtual_product_id: str
    tenant_id: str
    cycle_id: str
    refresh_id: str
    product_id: str
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    manufacturer_id: Optional[str] = None
    category_id: Optional[str] = None
    schedule_type: Optional[str] = None
    unit: Optional[str] = None
    is_active: bool
    snapshot_version: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# --------------------------------------------------------------------------
# Shared paginated envelope
# --------------------------------------------------------------------------

class Page(BaseModel):
    items: List[dict]
    total: int
    page: int
    page_size: int
