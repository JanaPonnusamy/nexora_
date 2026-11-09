"""Procurement Decision Engine — orchestration (Stages 0-6).

Turns a Refresh into an immutable, explainable Virtual Product List:

    Stage 0  Validate Refresh + load parameters   (PR-BR-016)
    Stage 1  Load source dataset (one bulk read)   (PR-BR-001/012/014 inputs)
    Stage 2-9 Quantity from the legacy local order query
              (legacy_order_parity), unless PROCUREMENT_GENERATION_PROFILE=nexora
    Stage 5  Bulk insert the VPL snapshot           (single executemany)
    Stage 6  Publish Refresh + point Cycle at it

Everything after Stage 0 runs inside one transaction so a Refresh is either
fully generated or not at all. The default quantity profile is the legacy
local order query (TotalStock, line frequency, single-line spike, Additional
Row zeroed). decision_rules.evaluate remains available as an explicit rollback.
"""

from dataclasses import replace

from fastapi import HTTPException

from config.database import get_connection
from modules.procurement import decision_repository as repo
from modules.procurement import decision_rules as rules
from modules.procurement import legacy_order_parity as legacy_parity

# Fields produced by decision_rules.evaluate that map 1:1 to VPL columns.
_OUTPUT_FIELDS = (
    "avg_daily_sales", "window_sales_qty", "max_day_sale_qty", "max_bill_qty",
    "billing_frequency", "current_stock_qty", "available_stock_qty",
    "pending_purchase_qty", "pending_sales_qty", "days_cover", "movement_class",
    "stock_status", "effective_available_qty", "pending_used_qty", "target_days",
    "target_stock_qty", "raw_required_qty", "required_qty", "suggested_qty",
    "final_required_qty", "procurement_action", "trigger_reason", "reason_code",
    "reason_text",
)


def _to_insert_row(tenant_id, refresh, src, out):
    """Merge product identity (source) with computed decision fields (out)."""
    row = {
        "tenant_id": tenant_id,
        "cycle_id": refresh["cycle_id"],
        "refresh_id": refresh["refresh_id"],
        "product_id": src.get("product_id"),
        "product_code": src.get("product_code"),
        "product_name": src.get("product_name"),
        "manufacturer_id": src.get("manufacturer_id"),
        "category_id": src.get("category_id"),
        "schedule_type": src.get("schedule_type"),
        "unit": src.get("unit"),
        "is_active": 1 if src.get("is_active", True) else 0,
        "snapshot_version": 1,
    }
    for field in _OUTPUT_FIELDS:
        row[field] = out[field]
    return row


def _num(value):
    """Coerce a DB numeric (pyodbc returns DECIMAL as decimal.Decimal) to float so
    the pure float rule engine never mixes float and Decimal operands."""
    return None if value is None else float(value)


def _load_parameters(refresh):
    """Stage 0: build + validate the effective parameter set (PR-BR-016)."""
    params = rules.DecisionParameters(
        rolling_days=int(refresh.get("rolling_days") or 90),
        min_days=_num(refresh.get("min_days")),
        max_days=_num(refresh.get("max_days")),
    )
    try:
        params.validate()
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Refresh has invalid decision parameters: {exc}",
        )
    return params


def generate_vpl(tenant_id, refresh_id):
    # Stage 0 — validate the Refresh and load parameters.
    refresh = repo.get_refresh_for_generation(tenant_id, refresh_id)
    if not refresh:
        raise HTTPException(status_code=404, detail="Refresh not found")
    if refresh["snapshot_status"] == "Archived":
        raise HTTPException(
            status_code=409, detail="Archived Refresh cannot be generated"
        )
    params = _load_parameters(refresh)
    profile = legacy_parity.generation_profile()
    if profile != legacy_parity.PROFILE_NEXORA:
        # Match the recency the legacy order job binds, not the Nexora engine's
        # historical default of 10.
        params = replace(params, recency_days=legacy_parity.bound_recency_days())

    conn = get_connection()
    try:
        repo.mark_generating(conn, tenant_id, refresh_id)

        # Stage 1 — load the source dataset once (no N+1).
        source = repo.load_source(conn, tenant_id, refresh.get("store_id"), params)

        # Persist products the legacy order list would contain: main lines and
        # Additional Row (buyer quantity 0). The Nexora rollback profile still
        # persists only decision_rules INCLUDE rows.
        rows, evaluated = [], 0
        for src in source:
            evaluated += 1
            if profile == legacy_parity.PROFILE_NEXORA:
                out = rules.evaluate(src, params)
            else:
                out = legacy_parity.evaluate_for_vpl(src, params, mode="local")
            if out["procurement_action"] == rules.ACTION_INCLUDE:
                rows.append(_to_insert_row(tenant_id, refresh, src, out))

        # Stage 5 — persist the immutable snapshot (bulk).
        repo.clear_products(conn, tenant_id, refresh_id)
        written = repo.bulk_insert_products(conn, rows)

        # Stage 6 — publish Refresh + point the Cycle at it.
        repo.finalize(conn, tenant_id, refresh_id, refresh["cycle_id"], written)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "refresh_id": str(refresh_id),
        "status": "Ready",
        # VPL now holds only procurement-eligible products, so written == included.
        "generated_product_count": written,
        "included_count": written,
        "excluded_count": evaluated - written,
        "evaluated_count": evaluated,
        "parameters": {
            "rolling_days": params.rolling_days,
            "min_days": params.min_days,
            "max_days": params.max_days,
            "recency_days": params.recency_days,
            "generation_profile": profile,
            "movement_fast_cut": params.movement_fast_cut,
            "movement_medium_cut": params.movement_medium_cut,
            "stock_low_cut": params.stock_low_cut,
            "stock_safe_cut": params.stock_safe_cut,
        },
    }
