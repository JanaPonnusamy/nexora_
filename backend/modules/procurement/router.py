"""HTTP routing for the Procurement module.

Exposes tenant-scoped CRUD for Procurement Cycles, plus the mounted Refresh
(VPL), Snapshot and Compare sub-routers. Mount `router` on the FastAPI app
(see register() / app wiring). The Workspace concept has been removed.
"""

from typing import Optional

from fastapi import APIRouter, Query

from modules.procurement import service
from modules.procurement.schemas import CycleCreate, CycleUpdate
from modules.procurement.vpl_router import router as vpl_router
from modules.procurement.snapshot_router import router as snapshot_router
from modules.procurement.compare_router import router as compare_router
from modules.procurement.orchestration_router import router as orchestration_router
from modules.procurement.pm_router import router as pm_router
from modules.procurement.pipeline_router import router as pipeline_router
from modules.procurement.intelligence_router import router as intelligence_router
from modules.procurement.optimization_router import router as optimization_router
from modules.procurement.reports.reports_router import router as reports_router

router = APIRouter(prefix="/api/procurement", tags=["Procurement"])

# End-to-end pipeline + manual product search (real synced data).
router.include_router(pipeline_router)
# Lifecycle orchestration — literal /cycles/open + /cycles/{id}/refreshes.
router.include_router(orchestration_router)
# Purchase Manager — workspace, supplier queue, assignment, export.
router.include_router(pm_router)
# Supplier Order Optimization — the stage between Auto Assignment and Export.
router.include_router(optimization_router)
# Product Intelligence — consolidated cross-store grid built from Refresh + VPL.
router.include_router(intelligence_router)
# Legacy Pharmacy Reports — read-only store business dashboard + monthly analysis.
router.include_router(reports_router)
# Comparison (runtime) — mounted FIRST so /vpl/compare resolves before the
# /vpl/{vpl_id} catch-all in the VPL router.
router.include_router(compare_router)
# Virtual Product List (owned by a Refresh) — mounted under /api/procurement/vpl
router.include_router(vpl_router)
# Snapshot Engine — /api/procurement/vpl/{vpl_id}/snapshot
router.include_router(snapshot_router)


# --------------------------------------------------------------------------
# Procurement Cycle
# --------------------------------------------------------------------------

@router.post("/cycles")
def create_cycle(payload: CycleCreate):
    return service.create_cycle(payload.dict())


@router.get("/cycles")
def list_cycles(
    tenant_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    return service.list_cycles(tenant_id, status, search, page, page_size, store_id)


@router.get("/cycles/{cycle_id}")
def get_cycle(cycle_id: str, tenant_id: str = Query(...)):
    return service.get_cycle(tenant_id, cycle_id)


@router.put("/cycles/{cycle_id}")
def update_cycle(
    cycle_id: str,
    payload: CycleUpdate,
    tenant_id: str = Query(...),
):
    return service.update_cycle(
        tenant_id, cycle_id, payload.dict(exclude_unset=True)
    )


@router.delete("/cycles/{cycle_id}")
def delete_cycle(
    cycle_id: str,
    tenant_id: str = Query(...),
    deleted_by: Optional[str] = Query(None),
):
    return service.delete_cycle(tenant_id, cycle_id, deleted_by)
