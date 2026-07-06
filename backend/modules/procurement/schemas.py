"""Pydantic request/response schemas for the Procurement module — Cycle.

Covers Procurement Cycle CRUD. No business logic (order calculation, supplier,
stock, pending, shortage, expiry) is modelled here — those belong to later
sprints. The Workspace concept has been removed from the approved model.
"""

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Procurement Cycle
# --------------------------------------------------------------------------

class CycleCreate(BaseModel):
    tenant_id: str
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    status: str = Field("DRAFT", max_length=50)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    # business boundary information (PR-BR-023 Store Completion)
    start_grn_number: Optional[str] = Field(None, max_length=50)
    start_sale_bill_number: Optional[str] = Field(None, max_length=50)
    end_grn_number: Optional[str] = Field(None, max_length=50)
    end_sale_bill_number: Optional[str] = Field(None, max_length=50)
    created_by: Optional[str] = None  # user_id (UNIQUEIDENTIFIER)


class CycleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    status: Optional[str] = Field(None, max_length=50)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    start_grn_number: Optional[str] = Field(None, max_length=50)
    start_sale_bill_number: Optional[str] = Field(None, max_length=50)
    end_grn_number: Optional[str] = Field(None, max_length=50)
    end_sale_bill_number: Optional[str] = Field(None, max_length=50)
    updated_by: Optional[str] = None  # user_id (UNIQUEIDENTIFIER)


class CycleOut(BaseModel):
    cycle_id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    status: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    start_grn_number: Optional[str] = None
    start_sale_bill_number: Optional[str] = None
    end_grn_number: Optional[str] = None
    end_sale_bill_number: Optional[str] = None
    active_refresh_id: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


# --------------------------------------------------------------------------
# Phase 4 — lifecycle orchestration
# --------------------------------------------------------------------------

class CycleOpen(BaseModel):
    """Open an ACTIVE Business Cycle (validated) and capture start boundaries."""
    tenant_id: str
    name: str = Field(..., min_length=1, max_length=200)
    # Procurement is always executed for a single store — mandatory.
    store_id: str = Field(..., min_length=1)
    description: Optional[str] = Field(None, max_length=1000)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    start_grn_number: Optional[str] = Field(None, max_length=50)
    start_sale_bill_number: Optional[str] = Field(None, max_length=50)
    created_by: str  # acting user (UNIQUEIDENTIFIER) — RBAC gate


class RefreshOrchestrate(BaseModel):
    """Create a Refresh and run the full pipeline (engine + working items)."""
    snapshot_name: Optional[str] = Field(None, max_length=200)
    rolling_days: Optional[int] = None
    min_days: float
    max_days: float
    previous_refresh_id: Optional[str] = None
    snapshot_grn_number: Optional[str] = Field(None, max_length=50)
    snapshot_sale_bill_number: Optional[str] = Field(None, max_length=50)
    sync_execution_id: Optional[str] = None
    created_by: Optional[str] = None  # user_id (UNIQUEIDENTIFIER)


# --------------------------------------------------------------------------
# Shared paginated envelope
# --------------------------------------------------------------------------

class Page(BaseModel):
    items: List[dict]
    total: int
    page: int
    page_size: int
