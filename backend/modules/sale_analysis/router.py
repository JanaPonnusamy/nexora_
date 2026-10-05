"""Sale Analysis API — grouped product-trend report (summary + detail).

Tenant-scoped like the other Inventory reports (a purchase manager may check any
store in their own tenant). Group definitions are persisted; the report itself is
read-only over ``sync.*``.
"""

from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from dependencies.auth import get_current_user
from dependencies.store_scope import assert_store_access
from modules.sale_analysis import repository as repo
from modules.sale_analysis import service
from modules.sale_analysis.schemas import GroupSaveRequest, SaleAnalysisResult

router = APIRouter(prefix="/api/sale-analysis", tags=["Sale Analysis"])


# --- lookups --------------------------------------------------------------

@router.get("/products")
def products(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    q: str = Query("", alias="q"),
    supplier_code: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Product search (name/code, optionally supplier-filtered) for the builder."""
    assert_store_access(current_user, tenant_id, store_id)
    return {"products": repo.search_products(tenant_id, store_id, q, supplier_code or None, limit)}


@router.get("/suppliers")
def suppliers(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    q: str = Query("", alias="q"),
    limit: int = Query(30, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    assert_store_access(current_user, tenant_id, store_id)
    return {"suppliers": repo.search_suppliers(tenant_id, store_id, q, limit)}


# --- group CRUD -----------------------------------------------------------

@router.get("/groups")
def list_groups(
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    assert_store_access(current_user, tenant_id)
    return {"groups": repo.list_groups(tenant_id)}


@router.get("/groups/{group_id}")
def get_group(
    group_id: str,
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    assert_store_access(current_user, tenant_id)
    g = repo.get_group(tenant_id, group_id)
    if not g:
        raise HTTPException(status_code=404, detail="group not found")
    return g


@router.post("/groups")
def create_group(
    tenant_id: str = Query(...),
    payload: GroupSaveRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
    assert_store_access(current_user, tenant_id)
    name = (payload.group_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="group_name is required")
    gid = repo.save_group(tenant_id, name, payload.product_names,
                          created_by=current_user.get("sub"))
    return repo.get_group(tenant_id, gid)


@router.put("/groups/{group_id}")
def update_group(
    group_id: str,
    tenant_id: str = Query(...),
    payload: GroupSaveRequest = Body(...),
    current_user: dict = Depends(get_current_user),
):
    assert_store_access(current_user, tenant_id)
    name = (payload.group_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="group_name is required")
    gid = repo.save_group(tenant_id, name, payload.product_names,
                          created_by=current_user.get("sub"), group_id=group_id)
    if not gid:
        raise HTTPException(status_code=404, detail="group not found")
    return repo.get_group(tenant_id, gid)


@router.delete("/groups/{group_id}")
def delete_group(
    group_id: str,
    tenant_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    assert_store_access(current_user, tenant_id)
    if not repo.delete_group(tenant_id, group_id):
        raise HTTPException(status_code=404, detail="group not found")
    return {"deleted": True}


# --- report ---------------------------------------------------------------

@router.get("/report", response_model=SaleAnalysisResult)
def report(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    group_id: List[str] = Query(default=[]),
    product_codes: Optional[str] = Query(None, description="comma-separated ad-hoc codes"),
    window: str = Query("month", description="month | last30 | range"),
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    target_days: int = Query(30, ge=1),
    current_user: dict = Depends(get_current_user),
):
    assert_store_access(current_user, tenant_id, store_id)
    adhoc = [c for c in (product_codes or "").split(",") if c.strip()]
    return service.run(tenant_id, store_id, group_id, adhoc, window,
                       from_date, to_date, target_days)
