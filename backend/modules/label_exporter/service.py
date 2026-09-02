"""Label Exporter service layer.

Thin pass-through to repository.py, which queries the real synced tables
(sync.Products / sync.Batches).
"""

from fastapi import HTTPException

from modules.label_exporter import repository

_VALID_INCLUDE_LABEL = {"Y", "N"}
_VALID_UNIT_DESCRIPTION_MODE = {"contains", "exact", "null"}


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
):
    if unit_description_mode not in _VALID_UNIT_DESCRIPTION_MODE:
        raise HTTPException(status_code=400, detail="Invalid unit_description_mode")
    result = repository.search_products(
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
    )
    result["unit_descriptions"] = repository.get_unit_descriptions(tenant_id, store_id, starts_with)
    return result


def search_boxes(tenant_id: str, store_id: str, q: str = "", starts_with: str = ""):
    return {"boxes": repository.search_boxes(tenant_id, store_id, q, starts_with)}


def get_box_products(tenant_id: str, store_id: str, box_number: str):
    return {"rows": repository.get_box_products(tenant_id, store_id, box_number)}


def get_product_batches(tenant_id: str, store_id: str, product_code: str):
    return {"rows": repository.get_product_batches(tenant_id, store_id, product_code)}


def update_review(
    tenant_id: str,
    store_id: str,
    product_code: str,
    include_label: str | None,
    remarks: str | None,
    user_id: str | None,
):
    if include_label is not None and include_label not in _VALID_INCLUDE_LABEL:
        raise HTTPException(status_code=400, detail="include_label must be 'Y' or 'N'")
    remarks = (remarks or "").strip() or None
    repository.upsert_review(tenant_id, store_id, product_code, include_label, remarks, user_id)


def assign_sublocation(tenant_id: str, store_id: str, product_code: str, sublocation: str, user_id: str | None):
    repository.assign_sublocation(tenant_id, store_id, product_code, sublocation.strip(), user_id)


def get_product_trend(tenant_id: str, store_id: str, product_code: str):
    return {"rows": repository.get_product_trend(tenant_id, store_id, product_code)}
