"""Label Exporter API.

Search products for label assignment, inspect box-wise product groupings, and
show batch-wise detail before exporting a printable label sheet from the UI.
Also carries the on-grid review workflow (Y/N include + remarks, open to any
store-scoped user) and the super-admin-only sublocation assignment + product
trend panel.
"""

from fastapi import APIRouter, Depends

from dependencies.auth import get_current_user
from dependencies.store_scope import assert_label_exporter_store_access, require_super_admin
from modules.label_exporter import service
from modules.label_exporter.schemas import (
    BoxProductResult,
    BoxSearchResult,
    LabelBulkReviewRequest,
    LabelPurchaseResult,
    LabelReviewUpdateRequest,
    LabelSaleResult,
    LabelSearchResult,
    LabelSublocationAssignRequest,
    LabelTrendResult,
    ProductBatchResult,
)

router = APIRouter(prefix="/api/label-exporter", tags=["Label Exporter"])


@router.get("/products/search", response_model=LabelSearchResult)
def search_products(
    tenant_id: str,
    store_id: str,
    q: str = "",
    starts_with: str = "",
    unit_description: str = "",
    unit_description_mode: str = "contains",
    box_number: str = "",
    stock_filter: str = "all",
    only_null_sublocation: int = 0,
    only_sale_unit_gt_one: int = 0,
    sublocation_filter: str = "",
    current_user: dict = Depends(get_current_user),
):
    assert_label_exporter_store_access(current_user, tenant_id, store_id)
    return service.search_products(
        tenant_id,
        store_id,
        q,
        starts_with,
        unit_description,
        unit_description_mode,
        box_number,
        stock_filter,
        only_null_sublocation,
        only_sale_unit_gt_one,
        sublocation_filter,
    )


@router.get("/boxes/search", response_model=BoxSearchResult)
def search_boxes(tenant_id: str, store_id: str, q: str = "", starts_with: str = "", current_user: dict = Depends(get_current_user)):
    assert_label_exporter_store_access(current_user, tenant_id, store_id)
    return service.search_boxes(tenant_id, store_id, q, starts_with)


@router.get("/boxes/products", response_model=BoxProductResult)
def get_box_products(tenant_id: str, store_id: str, box_number: str, current_user: dict = Depends(get_current_user)):
    assert_label_exporter_store_access(current_user, tenant_id, store_id)
    return service.get_box_products(tenant_id, store_id, box_number)


@router.get("/products/batches", response_model=ProductBatchResult)
def get_product_batches(tenant_id: str, store_id: str, product_code: str, current_user: dict = Depends(get_current_user)):
    assert_label_exporter_store_access(current_user, tenant_id, store_id)
    return service.get_product_batches(tenant_id, store_id, product_code)


@router.put("/products/{product_code}/review")
def update_review(
    tenant_id: str,
    store_id: str,
    product_code: str,
    body: LabelReviewUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    assert_label_exporter_store_access(current_user, tenant_id, store_id)
    service.update_review(
        tenant_id, store_id, product_code, body.include_label, body.remarks, current_user.get("sub")
    )
    return {"ok": True}


@router.put("/products/bulk-review")
def bulk_set_include_label(
    tenant_id: str,
    store_id: str,
    body: LabelBulkReviewRequest,
    current_user: dict = Depends(get_current_user),
):
    assert_label_exporter_store_access(current_user, tenant_id, store_id)
    service.bulk_set_include_label(
        tenant_id, store_id, body.product_codes, body.include_label, current_user.get("sub")
    )
    return {"ok": True, "count": len(body.product_codes)}


@router.put("/products/{product_code}/sublocation")
def assign_sublocation(
    tenant_id: str,
    store_id: str,
    product_code: str,
    body: LabelSublocationAssignRequest,
    current_user: dict = Depends(require_super_admin),
):
    service.assign_sublocation(tenant_id, store_id, product_code, body.sublocation, current_user.get("sub"))
    return {"ok": True}


@router.get("/products/{product_code}/trend", response_model=LabelTrendResult)
def get_product_trend(
    tenant_id: str,
    store_id: str,
    product_code: str,
    current_user: dict = Depends(get_current_user),
):
    assert_label_exporter_store_access(current_user, tenant_id, store_id)
    return service.get_product_trend(tenant_id, store_id, product_code)


@router.get("/products/{product_code}/purchases", response_model=LabelPurchaseResult)
def get_product_purchases(
    tenant_id: str,
    store_id: str,
    product_code: str,
    current_user: dict = Depends(get_current_user),
):
    assert_label_exporter_store_access(current_user, tenant_id, store_id)
    return service.get_product_purchases(tenant_id, store_id, product_code)


@router.get("/products/{product_code}/sales", response_model=LabelSaleResult)
def get_product_sales(
    tenant_id: str,
    store_id: str,
    product_code: str,
    current_user: dict = Depends(get_current_user),
):
    assert_label_exporter_store_access(current_user, tenant_id, store_id)
    return service.get_product_sales(tenant_id, store_id, product_code)
