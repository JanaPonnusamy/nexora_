"""HTTP routing for the Product Mapping module (prefix /api/product-mapping).

Tenant-scoped throughout (``tenant_id`` required query param), matching the
platform convention. Business rules live in the service/pure layers; this file
is validation + HTTP mapping only.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from dependencies.auth import get_current_user
from dependencies.store_scope import assert_tenant_access
from modules.product_mapping import dictionary_service, service
from modules.product_mapping.schemas import (
    ApproveRequest,
    BulkReviewRequest,
    DictionaryTermCreate,
    DictionaryTermUpdate,
    RejectRequest,
    RunRequest,
)

router = APIRouter(prefix="/api/product-mapping", tags=["Product Mapping"])


# --------------------------------------------------------------------------
# Engine runs
# --------------------------------------------------------------------------

@router.post("/runs")
def run_mapping(payload: RunRequest, tenant_id: str = Query(...), current_user: dict = Depends(get_current_user)):
    assert_tenant_access(current_user, tenant_id)
    try:
        return service.run_mapping(
            tenant_id, payload.source_store_id, payload.target_store_id, payload.actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --------------------------------------------------------------------------
# Mappings + review workflow
# --------------------------------------------------------------------------

@router.get("/mappings")
def list_mappings(
    tenant_id: str = Query(...),
    status: Optional[str] = Query(None),
    source_store_id: Optional[str] = Query(None),
    target_store_id: Optional[str] = Query(None),
    run_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.list_mappings(
        tenant_id, status=status, source_store_id=source_store_id,
        target_store_id=target_store_id, run_id=run_id, search=search,
        page=page, page_size=page_size)


@router.get("/mappings/{mapping_id}")
def get_mapping(mapping_id: str, tenant_id: str = Query(...), current_user: dict = Depends(get_current_user)):
    assert_tenant_access(current_user, tenant_id)
    detail = service.get_mapping_detail(tenant_id, mapping_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return detail


@router.get("/mappings/{mapping_id}/candidates")
def get_candidates(mapping_id: str, tenant_id: str = Query(...), current_user: dict = Depends(get_current_user)):
    assert_tenant_access(current_user, tenant_id)
    detail = service.get_mapping_detail(tenant_id, mapping_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return detail["candidates"]


@router.post("/mappings/{mapping_id}/approve")
def approve_mapping(mapping_id: str, payload: ApproveRequest, tenant_id: str = Query(...), current_user: dict = Depends(get_current_user)):
    assert_tenant_access(current_user, tenant_id)
    updated = service.approve_mapping(
        tenant_id, mapping_id, payload.actor,
        payload.target_product_code, payload.target_product_name)
    if not updated:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return updated


@router.post("/mappings/{mapping_id}/reject")
def reject_mapping(mapping_id: str, payload: RejectRequest, tenant_id: str = Query(...), current_user: dict = Depends(get_current_user)):
    assert_tenant_access(current_user, tenant_id)
    updated = service.reject_mapping(tenant_id, mapping_id, payload.actor)
    if not updated:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return updated


# --------------------------------------------------------------------------
# Manual Review v2 — bulk approve/reject + progress + product lookup
# --------------------------------------------------------------------------

@router.get("/manual-review/progress")
def manual_review_progress(
    tenant_id: str = Query(...),
    source_store_id: str = Query(...),
    target_store_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.review_progress(tenant_id, source_store_id, target_store_id)


@router.get("/manual-review/batch")
def manual_review_batch(
    tenant_id: str = Query(...),
    source_store_id: str = Query(...),
    target_store_id: str = Query(...),
    search: Optional[str] = Query(None),
    after_confidence: Optional[float] = Query(None),
    after_mapping_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Keyset-paginated PENDING batch for continuous Manual Review — pass back
    the previous batch's ``next_cursor`` fields to fetch the next one. Cost
    stays flat regardless of how deep into the queue the reviewer is."""
    assert_tenant_access(current_user, tenant_id)
    return service.review_batch(
        tenant_id, source_store_id, target_store_id, search=search,
        after_confidence=after_confidence, after_mapping_id=after_mapping_id, limit=limit)


@router.post("/manual-review/bulk")
def manual_review_bulk(payload: BulkReviewRequest, tenant_id: str = Query(...), current_user: dict = Depends(get_current_user)):
    assert_tenant_access(current_user, tenant_id)
    try:
        return service.bulk_review(
            tenant_id, payload.action,
            [i.dict() for i in payload.items],
            payload.source_store_id, payload.target_store_id,
            page=payload.page, page_size=payload.page_size, actor=payload.actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/products/search")
def search_products(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    query: str = Query("", alias="q"),
    limit: int = Query(25, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.search_products(tenant_id, store_id, query, limit)


# --------------------------------------------------------------------------
# Reusable lookups
# --------------------------------------------------------------------------

@router.get("/search")
def search_mapped(
    tenant_id: str = Query(...),
    source_store_id: str = Query(...),
    source_product_code: str = Query(...),
    target_store_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.search_mapped_product(
        tenant_id, source_store_id, source_product_code, target_store_id)


@router.get("/candidates")
def find_candidates(
    tenant_id: str = Query(...),
    target_store_id: str = Query(...),
    name: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=25),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.find_candidates(tenant_id, target_store_id, name, limit)


# --------------------------------------------------------------------------
# Dashboard / statistics / audit
# --------------------------------------------------------------------------

@router.get("/dashboard")
def dashboard(
    tenant_id: str = Query(...),
    source_store_id: Optional[str] = Query(None),
    target_store_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.dashboard(tenant_id, source_store_id, target_store_id)


@router.get("/statistics")
def statistics(
    tenant_id: str = Query(...),
    source_store_id: Optional[str] = Query(None),
    target_store_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.statistics(tenant_id, source_store_id, target_store_id)


@router.get("/audit")
def audit(
    tenant_id: str = Query(...),
    mapping_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.list_audit(tenant_id, mapping_id, page, page_size)


# --------------------------------------------------------------------------
# Normalization dictionary (configurable) — tenant_id is optional here
# (global terms apply platform-wide), so only a *supplied* tenant_id is
# checked against the caller's own tenant.
# --------------------------------------------------------------------------

@router.get("/dictionary")
def list_dictionary(tenant_id: Optional[str] = Query(None), current_user: dict = Depends(get_current_user)):
    if tenant_id:
        assert_tenant_access(current_user, tenant_id)
    return dictionary_service.list_terms(tenant_id)


@router.post("/dictionary")
def add_dictionary_term(payload: DictionaryTermCreate, tenant_id: Optional[str] = Query(None), current_user: dict = Depends(get_current_user)):
    if tenant_id:
        assert_tenant_access(current_user, tenant_id)
    try:
        entry_id = dictionary_service.add_term(
            tenant_id, payload.term, payload.canonical, payload.kind, payload.actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"entry_id": entry_id}


@router.put("/dictionary/{entry_id}")
def update_dictionary_term(entry_id: str, payload: DictionaryTermUpdate, current_user: dict = Depends(get_current_user)):
    fields = payload.dict(exclude_unset=True, exclude={"actor"})
    fields["actor"] = payload.actor
    try:
        dictionary_service.update_term(entry_id, **fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@router.delete("/dictionary/{entry_id}")
def delete_dictionary_term(entry_id: str, current_user: dict = Depends(get_current_user)):
    dictionary_service.delete_term(entry_id)
    return {"ok": True}
