"""Label Exporter API.

Search products for label assignment, inspect box-wise product groupings, and
show batch-wise detail before exporting a printable label sheet from the UI.
"""

from fastapi import APIRouter, Depends

from dependencies.auth import get_current_user
from dependencies.store_scope import assert_label_exporter_store_access
from modules.label_exporter import service
from modules.label_exporter.schemas import (
    BoxProductResult,
    BoxSearchResult,
    LabelSearchResult,
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
    box_number: str = "",
    stock_filter: str = "all",
    only_null_sublocation: int = 0,
    only_sale_unit_gt_one: int = 0,
    current_user: dict = Depends(get_current_user),
):
    assert_label_exporter_store_access(current_user, tenant_id, store_id)
    return service.search_products(
        tenant_id,
        store_id,
        q,
        starts_with,
        unit_description,
        box_number,
        stock_filter,
        only_null_sublocation,
        only_sale_unit_gt_one,
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
