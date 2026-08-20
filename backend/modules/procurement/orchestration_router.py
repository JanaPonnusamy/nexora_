"""HTTP routing for Procurement lifecycle orchestration (Phase 4).

Mounted onto the module's main `router` (which carries /api/procurement), so:
    POST /api/procurement/cycles/open
    POST /api/procurement/cycles/{cycle_id}/refreshes
"""

from fastapi import APIRouter, Query

from modules.procurement import orchestration_service as service
from modules.procurement.schemas import CycleOpen, RefreshOrchestrate
from modules.procurement.pm_schemas import CycleClose

router = APIRouter(tags=["Procurement Orchestration"])


@router.post("/cycles/open")
def open_business_cycle(payload: CycleOpen):
    """Validate preconditions and open an ACTIVE Business Cycle."""
    return service.create_business_cycle(payload.dict())


@router.post("/cycles/{cycle_id}/refreshes")
def create_refresh(
    cycle_id: str,
    payload: RefreshOrchestrate,
    tenant_id: str = Query(...),
):
    """Create a Refresh and run engine + working-item generation end to end."""
    return service.create_refresh(tenant_id, cycle_id, payload.dict())


@router.post("/refreshes/{refresh_id}/close")
def close_refresh(refresh_id: str, payload: CycleClose, tenant_id: str = Query(...)):
    """Lock a Refresh as read-only ('Closed') without closing its cycle. The
    console pairs this with a follow-up create_refresh to roll to Refresh N+1
    in the same open cycle."""
    return service.close_refresh(tenant_id, refresh_id, payload.closed_by)


@router.post("/cycles/{cycle_id}/close")
def close_cycle(cycle_id: str, payload: CycleClose, tenant_id: str = Query(...)):
    """Reconcile from synced purchases, auto-stamp End GRN / End Sale Bill, close
    the cycle and auto-open a fresh one. Returns ``status='pending_confirm'``
    when pending items remain and ``force`` was not set."""
    return service.close_cycle(
        tenant_id, cycle_id, payload.closed_by, force=payload.force,
    )
