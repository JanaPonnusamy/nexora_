"""HTTP routing for Procurement lifecycle orchestration (Phase 4).

Mounted onto the module's main `router` (which carries /api/procurement), so:
    POST /api/procurement/cycles/open
    POST /api/procurement/cycles/{cycle_id}/refreshes
    POST /api/procurement/stores/{store_id}/ensure-context
"""

from fastapi import APIRouter, Depends, Query

from dependencies.store_scope import assert_tenant_access
from modules.procurement import orchestration_service as service
from modules.procurement.access import require_procurement_workspace
from modules.procurement.schemas import CycleOpen, EnsureContext, RefreshOrchestrate
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


@router.post("/stores/{store_id}/ensure-context")
def ensure_context(
    store_id: str,
    payload: EnsureContext,
    tenant_id: str = Query(...),
    current_user: dict = Depends(require_procurement_workspace),
):
    """Get-or-create the store's active cycle and current refresh in one
    call, for the single-screen buyer entry flow — the buyer picks a store
    and lands directly in the workspace, with no separate cycle/refresh step."""
    assert_tenant_access(current_user, tenant_id)
    return service.ensure_active_context(tenant_id, store_id, payload.created_by)
