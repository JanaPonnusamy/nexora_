"""HTTP routing for the Supplier Order Optimization Engine.

Mounted onto the module's main router (/api/procurement). Covers the read-only
analysis (below-minimum suppliers + suggested moves), applying moves (Accept /
Accept All / Manual Move), the per-supplier Minimum Order Value config and the
move audit. No existing Procurement endpoint is changed.
"""

from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from modules.procurement import optimization_service as service

router = APIRouter(tags=["Procurement Optimization"])


# --- schemas ---------------------------------------------------------------

class MinOrderUpsert(BaseModel):
    store_id: str = Field(..., min_length=1)
    min_order_value: float = Field(..., ge=0)
    updated_by: Optional[str] = None


class MoveSpec(BaseModel):
    assignment_id: str = Field(..., min_length=1)
    to_supplier: str = Field(..., min_length=1, max_length=100)


class ApplyMovesRequest(BaseModel):
    moves: List[MoveSpec] = Field(..., min_length=1)
    reason: str = Field("auto", pattern="^(auto|manual)$")
    applied_by: Optional[str] = None


class ManualMoveRequest(BaseModel):
    assignment_id: str = Field(..., min_length=1)
    to_supplier: str = Field(..., min_length=1, max_length=100)
    moved_by: Optional[str] = None


# --- optimization analysis -------------------------------------------------

@router.get("/refreshes/{refresh_id}/optimization")
def optimization(
    refresh_id: str,
    tenant_id: str = Query(...),
    price_tolerance: float = Query(0.10, ge=0, le=1),
    use_live_stock: bool = Query(True),
):
    """Below-minimum suppliers + the lowest-value suggested moves to fix them,
    plus the full supplier summary. Read-only; runs in memory."""
    return service.analyze(tenant_id, refresh_id, price_tolerance, use_live_stock)


@router.post("/refreshes/{refresh_id}/optimization/apply")
def apply_moves(refresh_id: str, payload: ApplyMovesRequest, tenant_id: str = Query(...)):
    return service.apply_moves(
        tenant_id, refresh_id, [m.dict() for m in payload.moves],
        payload.applied_by, payload.reason,
    )


@router.post("/refreshes/{refresh_id}/optimization/manual-move")
def manual_move(refresh_id: str, payload: ManualMoveRequest, tenant_id: str = Query(...)):
    return service.manual_move(
        tenant_id, refresh_id, payload.assignment_id,
        payload.to_supplier, payload.moved_by,
    )


@router.get("/refreshes/{refresh_id}/optimization/audit")
def audit(refresh_id: str, tenant_id: str = Query(...)):
    return service.audit(tenant_id, refresh_id)


# --- Minimum Order Value config -------------------------------------------

@router.get("/suppliers/min-orders")
def list_min_orders(tenant_id: str = Query(...), store_id: str = Query(...)):
    return service.list_min_orders(tenant_id, store_id)


@router.put("/suppliers/{supplier_code}/min-order")
def set_min_order(
    supplier_code: str, payload: MinOrderUpsert, tenant_id: str = Query(...)
):
    return service.set_min_order(
        tenant_id, payload.store_id, supplier_code,
        payload.min_order_value, payload.updated_by,
    )
