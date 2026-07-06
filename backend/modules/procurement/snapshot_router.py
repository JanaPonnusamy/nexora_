"""HTTP routing for the Procurement Snapshot Engine — Sprint 3.

Mounted onto the module's main `router` (prefix /api/procurement), so paths
resolve under /api/procurement/vpl/{vpl_id}/snapshot.
"""

from typing import Optional

from fastapi import APIRouter, Query

from modules.procurement import snapshot_service as service

router = APIRouter(prefix="/vpl", tags=["Procurement Snapshot"])


@router.post("/{vpl_id}/snapshot")
def refresh_snapshot(
    vpl_id: str,
    tenant_id: str = Query(...),
    changed_only: bool = Query(False),
    refreshed_by: Optional[str] = Query(None),
):
    return service.refresh_vpl(tenant_id, vpl_id, refreshed_by, changed_only)


@router.post("/{vpl_id}/snapshot/{product_id}")
def refresh_snapshot_product(
    vpl_id: str,
    product_id: str,
    tenant_id: str = Query(...),
    refreshed_by: Optional[str] = Query(None),
):
    return service.refresh_product(tenant_id, vpl_id, product_id, refreshed_by)


@router.get("/{vpl_id}/snapshot/status")
def snapshot_status(vpl_id: str, tenant_id: str = Query(...)):
    return service.get_status(tenant_id, vpl_id)


@router.get("/{vpl_id}/snapshot/progress")
def snapshot_progress(vpl_id: str, tenant_id: str = Query(...)):
    return service.get_progress(tenant_id, vpl_id)
