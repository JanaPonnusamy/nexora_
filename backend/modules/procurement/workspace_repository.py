"""Data access for the Purchase Manager Workspace (Sprint 2, Modules 1-3).

Working source: procurement_order_items, joined to the immutable VPL for the
read-only decision context (movement class, stock status, days cover, reason).
The Purchase Manager may edit ONLY Final Quantity, Skip and Skip Reason — every
other field is read-only here. Skipped items are never deleted.
"""

from config.database import get_connection
from modules.procurement._dbutil import (
    as_uid as _as_uid,
    rows_to_dicts as _rows_to_dicts,
    stringify as _stringify,
)

# Columns the PM is allowed to sort by (whitelist — prevents SQL injection).
_SORTABLE = {
    "product_code": "oi.product_code",
    "product_name": "vp.product_name",
    "final_qty": "oi.final_qty",
    "remaining_qty": "oi.remaining_qty",
    "suggested_qty": "oi.suggested_qty",
    "item_status": "oi.item_status",
    "movement_class": "vp.movement_class",
    "stock_status": "vp.stock_status",
}

_SELECT = """
    oi.order_item_id, oi.tenant_id, oi.cycle_id, oi.refresh_id, oi.store_id,
    oi.product_id, oi.product_code, oi.is_manual,
    oi.suggested_qty, oi.final_qty, oi.assigned_qty, oi.remaining_qty,
    oi.item_status, oi.manual_override, oi.override_reason, oi.skip_reason,
    oi.reviewed_by, oi.reviewed_at,
    vp.product_name, vp.movement_class, vp.stock_status,
    vp.days_cover, vp.avg_daily_sales, vp.reason_code,
    COALESCE(NULLIF(RTRIM(vp.unit_description), ''), RTRIM(pr.UnitDescription)) AS unit_description,
    COALESCE(NULLIF(RTRIM(vp.pack), ''),
             CASE WHEN pr.SaleUnit IS NOT NULL THEN CAST(CAST(pr.SaleUnit AS INT) AS NVARCHAR(20)) END) AS pack,
    vp.mrp, vp.ptr_cost,
    vp.last_purchase_rate, vp.current_stock_qty,
    pr.ProductType AS product_type
"""

# oi.product_code and vp are joined by every caller; sync.Products (product
# master, ~hundreds of thousands of rows across all stores) is joined only to
# backfill Pack / Unit / Product Type when the VPL snapshot didn't capture them
# — COUNT(*) never needs it, so it gets its own leaner FROM below.
_FROM_BASE = """
    FROM procurement.procurement_order_items oi
    LEFT JOIN procurement.procurement_virtual_products vp
        ON vp.tenant_id = oi.tenant_id
       AND vp.refresh_id = oi.refresh_id
       AND vp.product_id = oi.product_id
"""

# sync.Products.ProductCode is INT (clustered PK is (store_id, ProductCode)).
# Casting BOTH sides to VARCHAR — as this join used to — defeats that index and
# forces a full clustered index scan of every store's product master on every
# workspace load. Casting only oi.product_code (varchar, one refresh's rows,
# never scanned on its own side) keeps pr.ProductCode bare so SQL Server can
# seek it directly.
_FROM = (
    _FROM_BASE
    + """
    LEFT JOIN sync.Products pr
        ON pr.tenant_id = oi.tenant_id
       AND pr.store_id = oi.store_id
       AND pr.ProductCode = TRY_CAST(oi.product_code AS INT)
"""
)

# Planning State — a direct SQL port of the PM grid's client-side classifier
# (was duplicated in the frontend as a JS function run over every loaded row on
# every render). Identical rule, computed once in the query instead: a skipped
# item is always 'skipped'; anything with a live assigned quantity is
# 'assigned'; a reviewed/partial item carrying a real Final Qty is 'finalized';
# everything else is still 'pending'.
_PLANNING_STATE_CASE = """
    CASE
        WHEN oi.item_status = 'skipped' THEN 'skipped'
        WHEN ISNULL(oi.assigned_qty, 0) > 0 THEN 'assigned'
        WHEN oi.item_status IN ('review', 'partial') AND ISNULL(oi.final_qty, 0) > 0 THEN 'finalized'
        ELSE 'pending'
    END
"""


def get_item(tenant_id, order_item_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_SELECT} {_FROM} "
            "WHERE oi.tenant_id = ? AND oi.order_item_id = ? AND oi.is_deleted = 0",
            (tenant_id, order_item_id),
        )
        rows = _rows_to_dicts(cursor)
        return _stringify(rows[0]) if rows else None
    finally:
        conn.close()


_DECISION_SELECT = """
    oi.order_item_id, oi.product_id, oi.product_code, oi.item_status,
    oi.suggested_qty AS oi_suggested_qty, oi.final_qty, oi.assigned_qty,
    oi.received_qty, oi.remaining_qty, oi.is_manual, oi.manual_override,
    oi.override_reason, oi.skip_reason, oi.pending_status,
    vp.product_name, vp.avg_daily_sales, vp.window_sales_qty,
    vp.max_day_sale_qty, vp.max_bill_qty, vp.current_stock_qty,
    vp.available_stock_qty, vp.effective_available_qty, vp.pending_used_qty,
    vp.days_cover, vp.movement_class, vp.stock_status,
    vp.target_days, vp.target_stock_qty, vp.raw_required_qty, vp.required_qty,
    vp.suggested_qty, vp.final_required_qty, vp.procurement_action,
    vp.trigger_reason, vp.reason_code, vp.reason_text
"""


def get_decision(tenant_id, order_item_id):
    """Full read-only decision snapshot for the Decision Explorer (Module 6)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # _DECISION_SELECT never references pr.* — skip the sync.Products join.
        cursor.execute(
            f"SELECT {_DECISION_SELECT} {_FROM_BASE} "
            "WHERE oi.tenant_id = ? AND oi.order_item_id = ? AND oi.is_deleted = 0",
            (tenant_id, order_item_id),
        )
        rows = _rows_to_dicts(cursor)
        return _stringify(rows[0]) if rows else None
    finally:
        conn.close()


def list_items(tenant_id, refresh_id, filters, sort_by, sort_dir, page, page_size):
    where = ["oi.tenant_id = ?", "oi.refresh_id = ?", "oi.is_deleted = 0"]
    params = [tenant_id, refresh_id]

    if filters.get("search"):
        where.append("(oi.product_code LIKE ? OR vp.product_name LIKE ?)")
        params.extend([f"%{filters['search']}%", f"%{filters['search']}%"])
    if filters.get("item_status"):
        where.append("oi.item_status = ?")
        params.append(filters["item_status"])
    if filters.get("movement_class"):
        where.append("vp.movement_class = ?")
        params.append(filters["movement_class"])
    if filters.get("stock_status"):
        where.append("vp.stock_status = ?")
        params.append(filters["stock_status"])
    if filters.get("is_manual") is not None:
        where.append("oi.is_manual = ?")
        params.append(1 if filters["is_manual"] else 0)
    # Planning State — was a client-side filter (the grid's 5 visibility
    # checkboxes) applied in JS over every already-downloaded row; now a real
    # server predicate so a page/paging change never has to guess how many
    # rows exist beyond the loaded window.
    planning_states = filters.get("planning_state")
    if planning_states:
        placeholders = ", ".join("?" for _ in planning_states)
        where.append(f"({_PLANNING_STATE_CASE}) IN ({placeholders})")
        params.extend(planning_states)
    # product_type reads sync.Products (pr) — only pull that join into the
    # query (COUNT included) when this filter is actually requested.
    needs_pr = bool(filters.get("product_type"))
    if needs_pr:
        where.append("pr.ProductType = ?")
        params.append(filters["product_type"])

    where_sql = " AND ".join(where)
    order_col = _SORTABLE.get(sort_by, "oi.product_code")
    order_dir = "DESC" if str(sort_dir).lower() == "desc" else "ASC"
    offset = (page - 1) * page_size
    count_from = _FROM if needs_pr else _FROM_BASE

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT COUNT(*) {count_from} WHERE {where_sql}", params
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            f"""
            SELECT {_SELECT} {_FROM}
            WHERE {where_sql}
            ORDER BY {order_col} {order_dir}
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            params + [offset, page_size],
        )
        items = [_stringify(r) for r in _rows_to_dicts(cursor)]
        return items, total
    finally:
        conn.close()


def get_summary(tenant_id, refresh_id, filters):
    """Refresh-wide counts for the PM footer — Total Products, Pending Review,
    Assigned, Finalized, Skipped — computed once in SQL instead of reducing
    over every loaded row in the browser. Scope matches what the footer has
    always shown: search + movement_class only, same as the grid's base load;
    the Planning State / Product Type / Manual filters are display filters for
    the grid and never narrowed these totals.

    Purchase Value is deliberately NOT computed here. The app's real per-row
    rate resolution (effectiveCost in purchaseValue.ts) falls back through the
    bulk supplier-recommendations ranking (supplier_repository.top_suppliers_bulk)
    before ever touching vp.last_purchase_rate/ptr_cost — confirmed against a
    real refresh where every oi/vp rate column was NULL yet the app correctly
    showed a non-zero total sourced entirely from that ranking. Reproducing it
    here would mean duplicating top_suppliers_bulk's query (itself carrying the
    same non-SARGable PurchaseTrans join Phase 2 fixed elsewhere) rather than
    reusing it. Purchase Value stays client-computed from the existing bulk
    recommendations feed until that ranking query has its own SARGable fix.
    """
    where = ["oi.tenant_id = ?", "oi.refresh_id = ?", "oi.is_deleted = 0"]
    params = [tenant_id, refresh_id]
    if filters.get("search"):
        where.append("(oi.product_code LIKE ? OR vp.product_name LIKE ?)")
        params.extend([f"%{filters['search']}%", f"%{filters['search']}%"])
    if filters.get("movement_class"):
        where.append("vp.movement_class = ?")
        params.append(filters["movement_class"])
    where_sql = " AND ".join(where)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT {_PLANNING_STATE_CASE} AS planning_state, COUNT(*) AS cnt
            {_FROM_BASE}
            WHERE {where_sql}
            GROUP BY {_PLANNING_STATE_CASE}
            """,
            params,
        )
        counts = {"pending": 0, "finalized": 0, "assigned": 0, "skipped": 0}
        for state, cnt in cursor.fetchall():
            if state in counts:
                counts[state] = cnt
        total = sum(counts.values())
        # "Pending Review" on the footer has always meant "not yet reviewed AND
        # not yet skipped" (item_status outside the reviewed set, qty still 0)
        # — a slightly different cut than the 'pending' planning-state bucket
        # (which only requires qty == 0, regardless of item_status). Compute it
        # with its own predicate so the footer number is unchanged.
        cursor.execute(
            f"""
            SELECT COUNT(*) {_FROM_BASE}
            WHERE {where_sql}
              AND oi.item_status NOT IN ('review', 'assigned', 'partial', 'skipped')
              AND ISNULL(oi.final_qty, 0) = 0
            """,
            params,
        )
        pending_review = cursor.fetchone()[0]
        return {
            "total": total,
            "pending_review": pending_review,
            "assigned": counts["assigned"],
            "finalized": counts["finalized"],
            "skipped": counts["skipped"],
        }
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Review edits — Final Quantity, Skip, Restore
# --------------------------------------------------------------------------

def _run(sql, params):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        affected = cursor.rowcount
        conn.commit()
        return affected
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_final_qty(tenant_id, order_item_id, final_qty, override_reason, reviewed_by):
    """Manual override: set Final Quantity; remaining = final - assigned."""
    reviewed_by = _as_uid(reviewed_by)  # NULL for a non-GUID display name
    return _run(
        """
        UPDATE procurement.procurement_order_items
        SET final_qty = ?,
            manual_override = 1,
            override_reason = ?,
            remaining_qty = ? - assigned_qty,
            item_status = 'review',
            skip_reason = NULL,
            reviewed_by = ?, reviewed_at = GETDATE(),
            updated_by = ?, updated_at = GETDATE()
        WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0
        """,
        (final_qty, override_reason, final_qty, reviewed_by, reviewed_by,
         tenant_id, order_item_id),
    )


def restore_suggested(tenant_id, order_item_id, reviewed_by):
    """Restore the engine's Suggested Quantity and clear the override."""
    reviewed_by = _as_uid(reviewed_by)  # NULL for a non-GUID display name
    return _run(
        """
        UPDATE procurement.procurement_order_items
        SET final_qty = suggested_qty,
            manual_override = 0,
            override_reason = NULL,
            remaining_qty = suggested_qty - assigned_qty,
            item_status = 'draft',
            reviewed_by = ?, reviewed_at = GETDATE(),
            updated_by = ?, updated_at = GETDATE()
        WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0
        """,
        (reviewed_by, reviewed_by, tenant_id, order_item_id),
    )


def skip_item(tenant_id, order_item_id, skip_reason, reviewed_by):
    reviewed_by = _as_uid(reviewed_by)  # NULL for a non-GUID display name
    return _run(
        """
        UPDATE procurement.procurement_order_items
        SET item_status = 'skipped',
            skip_reason = ?,
            final_qty = 0,
            remaining_qty = 0,
            reviewed_by = ?, reviewed_at = GETDATE(),
            updated_by = ?, updated_at = GETDATE()
        WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0
        """,
        (skip_reason, reviewed_by, reviewed_by, tenant_id, order_item_id),
    )


def restore_item(tenant_id, order_item_id, reviewed_by):
    """Un-skip back to Reviewed, keeping quantities.

    The PM workflow is Reviewed <-> Skipped (toggle freely until export), so a
    restore lands on 'review' regardless of override — the buyer sees the row
    return to Reviewed, not to an un-reviewed draft.
    """
    reviewed_by = _as_uid(reviewed_by)  # NULL for a non-GUID display name
    return _run(
        """
        UPDATE procurement.procurement_order_items
        SET item_status = 'review',
            skip_reason = NULL,
            reviewed_by = ?, reviewed_at = GETDATE(),
            updated_by = ?, updated_at = GETDATE()
        WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0
        """,
        (reviewed_by, reviewed_by, tenant_id, order_item_id),
    )
