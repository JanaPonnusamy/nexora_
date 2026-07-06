"""HTTP routing for the Virtual Product List (VPL) — Sprint 2.

This sub-router is mounted onto the module's main `router` (which carries the
/api/procurement prefix), so all paths below resolve under /api/procurement/vpl.
"""

from typing import Optional

from fastapi import APIRouter, Query

from modules.procurement import vpl_service as service
from modules.procurement import decision_service
from modules.procurement.vpl_schemas import VplCreate, VpProductAdd

router = APIRouter(prefix="/vpl", tags=["Procurement VPL"])


# --------------------------------------------------------------------------
# VPL header
# --------------------------------------------------------------------------

@router.post("")
def create_vpl(payload: VplCreate):
    return service.create_vpl(payload.dict())


@router.get("")
def list_vpls(
    tenant_id: str = Query(...),
    cycle_id: Optional[str] = Query(None),
    store_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    return service.list_vpls(
        tenant_id, cycle_id, store_id,
        status, search, page, page_size,
    )


@router.get("/{vpl_id}")
def get_vpl(vpl_id: str, tenant_id: str = Query(...)):
    return service.get_vpl(tenant_id, vpl_id)


@router.post("/{vpl_id}/refresh")
def refresh_vpl(
    vpl_id: str,
    tenant_id: str = Query(...),
    updated_by: Optional[str] = Query(None),
):
    return service.refresh_vpl(tenant_id, vpl_id, updated_by)


@router.post("/{vpl_id}/generate")
def generate_vpl(vpl_id: str, tenant_id: str = Query(...)):
    """Run the Decision Engine for this Refresh, producing the immutable VPL."""
    return decision_service.generate_vpl(tenant_id, vpl_id)


@router.post("/{vpl_id}/archive")
def archive_vpl(
    vpl_id: str,
    tenant_id: str = Query(...),
    updated_by: Optional[str] = Query(None),
):
    return service.archive_vpl(tenant_id, vpl_id, updated_by)


@router.delete("/{vpl_id}")
def delete_vpl(vpl_id: str, tenant_id: str = Query(...)):
    return service.delete_vpl(tenant_id, vpl_id)


# --------------------------------------------------------------------------
# VPL products
# --------------------------------------------------------------------------

@router.post("/{vpl_id}/products")
def add_product(
    vpl_id: str,
    payload: VpProductAdd,
    tenant_id: str = Query(...),
):
    return service.add_product(tenant_id, vpl_id, payload.dict())


@router.get("/{vpl_id}/products")
def list_products(
    vpl_id: str,
    tenant_id: str = Query(...),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    return service.list_products(tenant_id, vpl_id, search, page, page_size)


@router.delete("/{vpl_id}/products/{product_row_id}")
def remove_product(
    vpl_id: str,
    product_row_id: str,
    tenant_id: str = Query(...),
):
    return service.remove_product(tenant_id, vpl_id, product_row_id)
