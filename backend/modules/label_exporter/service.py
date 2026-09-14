"""Label Exporter service layer.

Thin pass-through to repository.py, which queries the real synced tables
(sync.Products / sync.Batches).
"""

import logging
import time

from fastapi import HTTPException

from modules.label_exporter import assignment_engine as engine
from modules.label_exporter import repository

logger = logging.getLogger("label_exporter.service")

_VALID_INCLUDE_LABEL = {"Y", "N"}
_VALID_UNIT_DESCRIPTION_MODE = {"contains", "exact", "null"}
_VALID_REVIEW_STATUS = {"", "unreviewed", "Y", "N"}
_VALID_MODE = {"continue", "new_label", "single"}
_VALID_ASSIGNMENT_TYPE = {"standard_box", "single_product_box"}


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
    review_status: str = "",
):
    if unit_description_mode not in _VALID_UNIT_DESCRIPTION_MODE:
        raise HTTPException(status_code=400, detail="Invalid unit_description_mode")
    if review_status not in _VALID_REVIEW_STATUS:
        raise HTTPException(status_code=400, detail="Invalid review_status")
    repository.ensure_schema()

    # Each stage opens its own DB connection (no pooling - see
    # config/database.get_connection), so a slow grid load can come from
    # network/connection overhead as easily as the query itself. Timed and
    # logged per-stage so a real "why is this slow" report doesn't require
    # reproducing it under a profiler.
    t0 = time.perf_counter()
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
        sublocation_filter,
        review_status,
    )
    t1 = time.perf_counter()
    result["unit_descriptions"] = repository.get_unit_descriptions(tenant_id, store_id, starts_with)
    t2 = time.perf_counter()
    result["sublocations"] = repository.get_sublocations(tenant_id, store_id)
    t3 = time.perf_counter()

    total_ms = (t3 - t0) * 1000
    logger.info(
        "search_products store=%s letter=%r q=%r rows=%d | products=%.0fms units=%.0fms sublocs=%.0fms total=%.0fms",
        store_id, starts_with, q, len(result["rows"]),
        (t1 - t0) * 1000, (t2 - t1) * 1000, (t3 - t2) * 1000, total_ms,
    )
    if total_ms > 2000:
        logger.warning(
            "search_products SLOW (%.0fms) store=%s letter=%r q=%r rows=%d",
            total_ms, store_id, starts_with, q, len(result["rows"]),
        )
    result["server_ms"] = round(total_ms)
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


def bulk_set_include_label(
    tenant_id: str, store_id: str, product_codes: list[str], include_label: str, user_id: str | None
):
    if include_label not in _VALID_INCLUDE_LABEL:
        raise HTTPException(status_code=400, detail="include_label must be 'Y' or 'N'")
    repository.bulk_set_include_label(tenant_id, store_id, product_codes, include_label, user_id)


def assign_sublocation(tenant_id: str, store_id: str, product_code: str, sublocation: str, user_id: str | None):
    repository.assign_sublocation(tenant_id, store_id, product_code, sublocation.strip(), user_id)


def correct_location(
    tenant_id: str, store_id: str, product_code: str, location: str, current_location: str, user_id
):
    """Manual single-product box override -- bypasses the standard-box/SYP
    assignment engine entirely (see repository.correct_location)."""
    new_location = (location or "").strip().upper()
    if not new_location:
        raise HTTPException(status_code=400, detail="location is required")
    repository.ensure_schema()
    repository.correct_location(
        tenant_id, store_id, product_code, new_location, (current_location or "").strip().upper() or None, user_id
    )


def get_product_trend(tenant_id: str, store_id: str, product_code: str):
    return {"rows": repository.get_product_trend(tenant_id, store_id, product_code)}


def get_product_purchases(tenant_id: str, store_id: str, product_code: str):
    return {"rows": repository.get_product_purchases(tenant_id, store_id, product_code)}


def get_product_sales(tenant_id: str, store_id: str, product_code: str):
    return {"rows": repository.get_product_sales(tenant_id, store_id, product_code)}


# --------------------------------------------------------------------------
# Unit correction (auto-save)
# --------------------------------------------------------------------------

def correct_unit(
    tenant_id: str, store_id: str, product_code: str, unit_description: str, current_unit: str, user_id
):
    new_unit = (unit_description or "").strip().upper()
    if not new_unit:
        raise HTTPException(status_code=400, detail="unit_description is required")
    repository.ensure_schema()
    repository.correct_unit(
        tenant_id, store_id, product_code, new_unit, (current_unit or "").strip().upper() or None, user_id
    )


# --------------------------------------------------------------------------
# Location assignment (preview + commit share one plan builder)
# --------------------------------------------------------------------------

def _build_assignment_plan(
    tenant_id, store_id, unit, mode, assignment_type, letter, product_codes, start_number
):
    """Shared, backend-authoritative planner (spec §AG): the frontend never
    computes the final boxes - it previews and commits through here, and both
    paths run the identical engine. Returns (plan, enriched_assignments)."""
    repository.ensure_schema()
    mode = (mode or "continue").strip()
    assignment_type = (assignment_type or "standard_box").strip()
    unit_u = (unit or "").strip().upper()
    letter = (letter or "").strip().upper()[:1]

    if mode not in _VALID_MODE:
        raise HTTPException(status_code=400, detail="Invalid assignment mode")
    if assignment_type not in _VALID_ASSIGNMENT_TYPE:
        raise HTTPException(status_code=400, detail="Invalid assignment type")
    codes = [c for c in (product_codes or []) if str(c or "").strip()]
    if not codes:
        raise HTTPException(status_code=400, detail="No products selected for assignment")

    products_raw = repository.get_products_for_assignment(tenant_id, store_id, codes)
    found = {p["product_code"] for p in products_raw}
    missing = [c for c in codes if c not in found]
    if missing:
        # tenant/store safety: a code not present in THIS store is rejected
        raise HTTPException(
            status_code=400,
            detail=f"{len(missing)} product(s) not found in this store and cannot be assigned",
        )

    products = [engine.Product(p["product_code"], p["product_name"]) for p in products_raw]
    meta_by_code = {p["product_code"]: p for p in products_raw}

    try:
        if assignment_type == "single_product_box":
            if not letter:
                raise HTTPException(status_code=400, detail="A letter is required for box numbering")
            occ = repository.get_box_occupancy(tenant_id, store_id, letter, exclude_codes=codes)
            plan = engine.plan_single_boxes(letter, products, occ)
        elif unit_u == engine.UNIT_SYP:
            plan = engine.plan_syp(products)
        elif unit_u == engine.UNIT_TAB:
            if not letter:
                raise HTTPException(status_code=400, detail="A letter is required for TAB assignment")
            if mode == "new_label":
                plan = engine.plan_new_label(letter, products, start_number=int(start_number or 1))
            else:
                occ = repository.get_box_occupancy(tenant_id, store_id, letter, exclude_codes=codes)
                plan = engine.plan_continue(letter, products, occ)
        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No automatic location rule for unit '{unit}'. Use Single Product Box "
                    "or assign these manually."
                ),
            )
        engine.validate_plan(plan)
    except engine.AssignmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    enriched = []
    for a in plan.assignments:
        meta = meta_by_code.get(a.product_code, {})
        enriched.append(
            {
                "product_code": a.product_code,
                "product_name": a.product_name,
                "box": a.box,
                "slot": a.slot,
                "unit_description": meta.get("unit_description"),
                "old_location": meta.get("current_location"),
                "stock": meta.get("stock"),
            }
        )
    return plan, enriched


def preview_assignment(
    tenant_id, store_id, unit, mode, assignment_type, letter, product_codes, start_number=1
):
    plan, _ = _build_assignment_plan(
        tenant_id, store_id, unit, mode, assignment_type, letter, product_codes, start_number
    )
    return plan.to_dict()


def commit_assignment(
    tenant_id, store_id, unit, mode, assignment_type, letter, product_codes, start_number, user_id
):
    plan, enriched = _build_assignment_plan(
        tenant_id, store_id, unit, mode, assignment_type, letter, product_codes, start_number
    )
    repository.assign_locations(tenant_id, store_id, enriched, plan.mode, plan.assignment_type, user_id)
    result = plan.to_dict()
    result["committed"] = True
    return result


# --------------------------------------------------------------------------
# Label queue (print stays separate from assignment)
# --------------------------------------------------------------------------

def get_label_queue(tenant_id: str, store_id: str):
    repository.ensure_schema()
    return {"rows": repository.get_label_queue(tenant_id, store_id)}


def mark_labels_printed(tenant_id: str, store_id: str, product_codes: list[str]):
    repository.ensure_schema()
    repository.mark_labels_printed(tenant_id, store_id, product_codes)
    return {"ok": True, "count": len(product_codes or [])}


# --------------------------------------------------------------------------
# Explicit reset actions (spec §10/§11) — label_review only, never master data
# --------------------------------------------------------------------------

def clear_assignment_state(tenant_id: str, store_id: str, product_codes: list[str]):
    codes = [c for c in (product_codes or []) if str(c or "").strip()]
    if not codes:
        raise HTTPException(status_code=400, detail="No products selected")
    repository.ensure_schema()
    affected = repository.clear_assignment_state(tenant_id, store_id, codes)
    return {"ok": True, "count": len(codes), "affected": affected}


def clear_review_state(tenant_id: str, store_id: str, product_codes: list[str]):
    codes = [c for c in (product_codes or []) if str(c or "").strip()]
    if not codes:
        raise HTTPException(status_code=400, detail="No products selected")
    repository.ensure_schema()
    affected = repository.clear_review_state(tenant_id, store_id, codes)
    return {"ok": True, "count": len(codes), "affected": affected}
