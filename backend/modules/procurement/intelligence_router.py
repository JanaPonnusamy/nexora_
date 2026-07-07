"""HTTP routing for the Product Intelligence Workspace.

Mounted onto the module's main `router` (which carries /api/procurement), so
every path resolves under /api/procurement/intelligence. The UI reads the cache
only; the sole on-demand transaction read is the hover endpoint.
"""

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from modules.procurement import intelligence_service as service

router = APIRouter(prefix="/intelligence", tags=["Procurement Product Intelligence"])


class BuildRequest(BaseModel):
    tenant_id: str
    refresh_id: Optional[str] = None
    created_by: Optional[str] = None


@router.post("/build")
def build(payload: BuildRequest):
    """Build the Product Intelligence cache from the latest Refresh + VPL."""
    return service.build_intelligence(
        payload.tenant_id, payload.refresh_id, payload.created_by
    )


@router.get("")
def grid(
    tenant_id: str = Query(...),
    refresh_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    """The dynamic grid (store columns + consolidated rows with per-store cells)."""
    return service.get_grid(tenant_id, refresh_id, search)


@router.get("/summary")
def summary(tenant_id: str = Query(...), refresh_id: Optional[str] = Query(None)):
    """Roll-up: total products, purchase / transfer / stock quantities."""
    return service.get_summary(tenant_id, refresh_id)


@router.get("/{cache_id}")
def detail(cache_id: str):
    """Per-product detail + full cross-store stock distribution."""
    return service.get_detail(cache_id)


@router.get("/{cache_id}/stores")
def stores(cache_id: str):
    """Dynamic per-store metrics for one product."""
    return service.get_stores(cache_id)


@router.get("/{cache_id}/hover/{store_id}")
def hover(cache_id: str, store_id: str):
    """On-demand hover: last sale/purchase, sales + purchase history, non-moving."""
    return service.get_hover(cache_id, store_id)
