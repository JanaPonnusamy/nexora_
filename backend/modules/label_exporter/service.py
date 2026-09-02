"""Label Exporter service layer.

Thin pass-through to repository.py, which queries the real synced tables
(sync.Products / sync.Batches).
"""

from fastapi import HTTPException

from modules.label_exporter import repository

_VALID_INCLUDE_LABEL = {"Y", "N"}
_VALID_PRODUCT_KIND = {"counter", "consumer"}


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
):
    result = repository.search_products(
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
    result["unit_descriptions"] = repository.get_unit_descriptions(tenant_id, store_id, starts_with)
    return result


def search_boxes(tenant_id: str, store_id: str, q: str = "", starts_with: str = ""):
    return {"boxes": repository.search_boxes(tenant_id, store_id, q, starts_with)}


def get_box_products(tenant_id: str, store_id: str, box_number: str):
    return {"rows": repository.get_box_products(tenant_id, store_id, box_number)}


def get_product_batches(tenant_id: str, store_id: str, product_code: str):
    return {"rows": repository.get_product_batches(tenant_id, store_id, product_code)}


def list_products_for_review(tenant_id: str, store_id: str, starts_with: str = ""):
    return {"rows": repository.list_products_for_review(tenant_id, store_id, starts_with)}


def update_review(
    tenant_id: str,
    store_id: str,
    product_code: str,
    include_label: str | None,
    product_kind: str | None,
    suggested_unit_description: str | None,
    user_id: str | None,
):
    if include_label is not None and include_label not in _VALID_INCLUDE_LABEL:
        raise HTTPException(status_code=400, detail="include_label must be 'Y' or 'N'")
    if product_kind is not None and product_kind not in _VALID_PRODUCT_KIND:
        raise HTTPException(status_code=400, detail="product_kind must be 'counter' or 'consumer'")
    suggestion = (suggested_unit_description or "").strip() or None
    repository.upsert_review(
        tenant_id, store_id, product_code, include_label, product_kind, suggestion, user_id
    )


def list_pending_suggestions(tenant_id: str = "", store_id: str = ""):
    return {"rows": repository.list_pending_suggestions(tenant_id, store_id)}


def decide_suggestion(
    tenant_id: str,
    store_id: str,
    product_code: str,
    approved: bool,
    final_unit_description: str | None,
    user_id: str | None,
):
    final = (final_unit_description or "").strip() or None
    if approved and not final:
        raise HTTPException(status_code=400, detail="final_unit_description is required to approve")
    repository.decide_suggestion(tenant_id, store_id, product_code, approved, final, user_id)
