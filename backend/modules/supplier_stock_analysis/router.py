"""Standalone Supplier Stock Analysis API."""

import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from dependencies.auth import get_current_user
from dependencies.store_scope import assert_tenant_access
from modules.supplier_stock_analysis import service
from modules.supplier_stock_analysis.schemas import MappingUpdate

router = APIRouter(prefix="/api/supplier-stock-analysis", tags=["Supplier Stock Analysis"])


@router.get("/suppliers")
def suppliers(tenant_id: str, store_id: Optional[str] = None, search: str = "", current_user: dict = Depends(get_current_user)):
    assert_tenant_access(current_user, tenant_id)
    return service.list_suppliers(tenant_id, store_id, search)


@router.get("/supplier-products")
def supplier_products(
    tenant_id: str,
    supplier_code: str,
    store_id: Optional[str] = None,
    search: str = "",
    only_available: int = 1,
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.list_supplier_products(
        tenant_id, supplier_code, store_id, search, only_available == 1
    )


@router.get("/supplier-stock/{supplier_stock_id}/match")
def supplier_stock_match(supplier_stock_id: str, tenant_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    return service.match_for_supplier_stock(current_user, supplier_stock_id, tenant_id)


@router.get("/supplier-report")
def supplier_report(
    tenant_id: str,
    supplier_code: str,
    store_id: Optional[str] = None,
    only_available: int = 0,
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.supplier_analysis_report(
        tenant_id, supplier_code, store_id, only_available == 1
    )


@router.get("/supplier-stock/{supplier_stock_id}/dashboard")
def supplier_stock_dashboard(
    supplier_stock_id: str,
    tenant_id: Optional[str] = None,
    months: int = 6,
    current_user: dict = Depends(get_current_user),
):
    return service.supplier_stock_dashboard(current_user, supplier_stock_id, tenant_id, months)


@router.get("/supplier-stock/{supplier_stock_id}/dashboard/stock")
def supplier_stock_dashboard_stock(
    supplier_stock_id: str,
    tenant_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    return service.supplier_stock_dashboard_stock(current_user, supplier_stock_id, tenant_id)


@router.get("/supplier-stock/{supplier_stock_id}/dashboard/details")
def supplier_stock_dashboard_details(
    supplier_stock_id: str,
    tenant_id: str,
    source_store_id: str,
    product_code: str,
    months: int = 6,
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.supplier_stock_dashboard_details(tenant_id, source_store_id, product_code, months)


@router.get("/supplier-stock/{supplier_stock_id}/family")
def supplier_stock_family(supplier_stock_id: str, tenant_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    return service.family_for_supplier_stock(current_user, supplier_stock_id, tenant_id)


@router.get("/search")
def global_search(
    tenant_id: str,
    query: str = "",
    store_id: Optional[str] = None,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.global_search(tenant_id, query, store_id, limit)


@router.get("/products/{product_code}/dashboard")
def product_dashboard(
    tenant_id: str,
    source_store_id: str,
    product_code: str,
    months: int = 6,
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    return service.product_dashboard(tenant_id, source_store_id, product_code, months)


@router.post("/mapping")
def update_mapping(payload: MappingUpdate, current_user: dict = Depends(get_current_user)):
    assert_tenant_access(current_user, payload.tenant_id)
    return service.update_mapping(payload.dict())


@router.post("/excel/preview")
async def excel_preview(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    data = await file.read()
    return service.preview_excel(data)


@router.post("/excel/import")
async def excel_import(
    tenant_id: str = Form(...),
    store_id: str = Form(...),
    supplier_code: str = Form(...),
    mapping_json: str = Form(...),
    imported_by: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    assert_tenant_access(current_user, tenant_id)
    data = await file.read()
    mapping = json.loads(mapping_json)
    return service.import_excel(
        tenant_id, store_id, supplier_code, data, mapping, imported_by
    )
