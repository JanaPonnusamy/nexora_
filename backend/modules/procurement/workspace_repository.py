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

# sync.Products (product master) supplies Pack (SaleUnit) / Unit (UnitDescription)
# / Product Type when the immutable VPL snapshot did not capture them.
_FROM = """
    FROM procurement.procurement_order_items oi
    LEFT JOIN procurement.procurement_virtual_products vp
        ON vp.tenant_id = oi.tenant_id
       AND vp.refresh_id = oi.refresh_id
       AND vp.product_id = oi.product_id
    LEFT JOIN sync.Products pr
        ON pr.tenant_id = oi.tenant_id
       AND pr.store_id = oi.store_id
       AND CAST(pr.ProductCode AS VARCHAR(100)) = CAST(oi.product_code AS VARCHAR(100))
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
        cursor.execute(
            f"SELECT {_DECISION_SELECT} {_FROM} "
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

    where_sql = " AND ".join(where)
    order_col = _SORTABLE.get(sort_by, "oi.product_code")
    order_dir = "DESC" if str(sort_dir).lower() == "desc" else "ASC"
    offset = (page - 1) * page_size

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT COUNT(*) {_FROM} WHERE {where_sql}", params
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
