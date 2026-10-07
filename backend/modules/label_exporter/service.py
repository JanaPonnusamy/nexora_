"""Label Exporter service layer.

Thin pass-through to repository.py, which queries the real synced tables
(sync.Products / sync.Batches).
"""

import logging
import time

from fastapi import HTTPException

from modules.label_exporter import assignment_engine as engine
from modules.label_exporter import pdf_export
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


def bulk_correct_unit(
    tenant_id: str, store_id: str, product_codes: list[str], unit_description: str, user_id
):
    """Find-and-replace a unit across many products (e.g. all selected RM rows
    -> TAB). The original master unit is captured into old_unit_description
    once per product (never overwritten), exactly like the single-row path."""
    new_unit = (unit_description or "").strip().upper()
    if not new_unit:
        raise HTTPException(status_code=400, detail="unit_description is required")
    codes = [c for c in (product_codes or []) if str(c or "").strip()]
    if not codes:
        raise HTTPException(status_code=400, detail="No products selected")
    repository.ensure_schema()
    affected = repository.bulk_correct_unit(tenant_id, store_id, codes, new_unit, user_id)
    return {"ok": True, "count": len(codes), "affected": affected}


# --------------------------------------------------------------------------
# Location assignment (preview + commit share one plan builder)
# --------------------------------------------------------------------------

def _occupancy_for_letters(tenant_id, store_id, letters, exclude_codes):
    """Merge per-letter occupancy maps into one {box: count} dict covering every
    letter in a multi-letter selection (Continue/Single need live occupancy;
    New-from-1 ignores it). A handful of letters, one query each."""
    occ: dict[str, int] = {}
    for one in letters:
        if not one or not str(one).isalpha():
            continue
        occ.update(repository.get_box_occupancy(tenant_id, store_id, one, exclude_codes=exclude_codes))
    return occ


def _letter_specs_from(letter_plans):
    """Turn the request's [{letter, mode, start_number}, ...] into
    {LETTER: {"mode", "start_number"}} for the engine, validating modes."""
    specs: dict[str, dict] = {}
    for lp in letter_plans or []:
        one = str(getattr(lp, "letter", "") or "").strip().upper()[:1]
        if not one:
            continue
        mode = str(getattr(lp, "mode", "") or "continue").strip()
        if mode not in _VALID_MODE:
            raise HTTPException(status_code=400, detail=f"Invalid mode for letter {one}")
        specs[one] = {"mode": mode, "start_number": int(getattr(lp, "start_number", 1) or 1)}
    return specs


def _build_assignment_plan(
    tenant_id, store_id, unit, mode, assignment_type, letter, product_codes, start_number, letter_plans=None
):
    """Shared, backend-authoritative planner (spec §AG): the frontend never
    computes the final boxes - it previews and commits through here, and both
    paths run the identical engine. Each product is boxed under its OWN first
    letter, and each letter can run its own mode (from ``letter_plans``), so a
    multi-letter selection is never dumped under one letter. Returns
    (plan, enriched_assignments)."""
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
    specs = _letter_specs_from(letter_plans)

    # A legacy global "Single Product Box" choice means every letter is single.
    default_mode = engine.LETTER_MODE_SINGLE if assignment_type == "single_product_box" else mode

    try:
        if unit_u == engine.UNIT_SYP:
            # SYP ignores per-letter modes — it always buckets into SYP<letter>.
            plan = engine.plan_syp(products)
        elif unit_u in engine.STANDARD_BOX_UNITS:
            letters = engine.letters_in(products, fallback=letter)
            # Occupancy only for letters that will Continue/Single (New-from-1 skips it).
            need_occ = [
                one for one in letters
                if (specs.get(one, {}).get("mode", default_mode)) in (engine.LETTER_MODE_CONTINUE, engine.LETTER_MODE_SINGLE)
            ]
            occ = _occupancy_for_letters(tenant_id, store_id, need_occ, codes) if need_occ else {}
            plan = engine.plan_by_letter(
                products, specs, occ,
                default_mode=default_mode,
                default_start=int(start_number or 1),
                unit=unit_u,
                fallback_letter=letter,
            )
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
                # Per-row mode/type so a mixed (per-letter) run audits honestly.
                "mode": a.mode or plan.mode,
                "assignment_type": "single_product_box" if a.mode == engine.LETTER_MODE_SINGLE else "standard_box",
                "unit_description": meta.get("unit_description"),
                "old_location": meta.get("current_location"),
                "stock": meta.get("stock"),
            }
        )
    return plan, enriched


def preview_assignment(
    tenant_id, store_id, unit, mode, assignment_type, letter, product_codes, start_number=1, letter_plans=None
):
    plan, _ = _build_assignment_plan(
        tenant_id, store_id, unit, mode, assignment_type, letter, product_codes, start_number, letter_plans
    )
    return plan.to_dict()


def commit_assignment(
    tenant_id, store_id, unit, mode, assignment_type, letter, product_codes, start_number, user_id, letter_plans=None
):
    plan, enriched = _build_assignment_plan(
        tenant_id, store_id, unit, mode, assignment_type, letter, product_codes, start_number, letter_plans
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


def clear_printed_state(tenant_id: str, store_id: str, product_codes: list[str]):
    codes = [c for c in (product_codes or []) if str(c or "").strip()]
    if not codes:
        raise HTTPException(status_code=400, detail="No products selected")
    repository.ensure_schema()
    affected = repository.clear_printed_state(tenant_id, store_id, codes)
    return {"ok": True, "count": len(codes), "affected": affected}


def build_label_queue_pdf(tenant_id: str, store_id: str, letter: str | None = None) -> bytes:
    repository.ensure_schema()
    rows = repository.get_label_queue(tenant_id, store_id)
    return pdf_export.build_label_queue_pdf(rows, letter)


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
