"""HTTP routing for the Product Intelligence Workspace (network-wide).

Mounted onto the module's main `router` (which carries /api/procurement), so
every path resolves under /api/procurement/intelligence. The grid is served from
the cache; the only on-demand transaction reads are the per-store history and the
per-store charts, both opened from the detail panel.
"""

from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from modules.procurement import intelligence_service as service

router = APIRouter(prefix="/intelligence", tags=["Procurement Product Intelligence"])


class BuildRequest(BaseModel):
    tenant_id: str
    # The purchasing warehouse — the store the final procurement quantity is FOR.
    warehouse_store_id: str
    # The stores refreshed in this run; omitted = every active store with a VPL.
    store_ids: Optional[List[str]] = None
    created_by: Optional[str] = None


@router.post("/build")
def build(payload: BuildRequest):
    """Consolidate EVERY selected store's VPL into the network procurement grid."""
    return service.build_intelligence(
        payload.tenant_id, payload.warehouse_store_id,
        payload.store_ids, payload.created_by,
    )


@router.get("")
def grid(
    tenant_id: str = Query(...),
    build_id: Optional[str] = Query(None),
    warehouse_store_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    """The grid: one row per canonical supplier product, with per-store cells."""
    return service.get_grid(tenant_id, build_id, warehouse_store_id, search)


@router.get("/summary")
def summary(
    tenant_id: str = Query(...),
    build_id: Optional[str] = Query(None),
    warehouse_store_id: Optional[str] = Query(None),
):
    """Roll-up: products, network need, purchase / transfer / stock quantities."""
    return service.get_summary(tenant_id, build_id, warehouse_store_id)


@router.get("/{cache_id}")
def detail(cache_id: str):
    """Per-product detail: the network decision + every store's position."""
    return service.get_detail(cache_id)


@router.get("/{cache_id}/stores")
def stores(cache_id: str):
    """The stores this canonical product exists in (the detail store selector)."""
    return service.get_stores(cache_id)


@router.get("/{cache_id}/charts")
def charts(cache_id: str, months: int = Query(4, ge=1, le=24)):
    """Every store's last-N-month transaction chart in one payload — each store
    resolved independently BY PRODUCT NAME, on a shared month axis."""
    return service.get_store_charts(cache_id, months)


@router.get("/{cache_id}/history/{store_id}")
def history(cache_id: str, store_id: str, months: int = Query(12, ge=1, le=36)):
    """Sales + purchase history for ONE store — loaded only when the user opens
    that store, never for every store at once."""
    return service.get_store_history(cache_id, store_id, months)
