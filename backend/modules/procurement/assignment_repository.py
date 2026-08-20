"""Data access for Supplier Assignment (Sprint 2, Module 5).

An order item may carry at most ONE active assignment — one product, one
supplier per cycle (enforced in assignment_service via any_active_assignment).
Reassigning to a different supplier goes through change_supplier, never a
second insert. All writes run on a caller-owned connection so a bulk
assignment is atomic. After any assignment change the owning order item's
assigned_qty / remaining_qty / item_status are recomputed from the live
assignments (single source of truth — no duplicated totals).
"""

import math

from config.database import get_connection
from modules.procurement._dbutil import (
    as_uid as _as_uid,
    rows_to_dicts as _rows_to_dicts,
    stringify as _stringify,
)


def _format_offer_ratio(stockreceived, free_qty):
    """"Buy X get Y free" from a PurchaseTrans row's stockreceived/FreeQty,
    reduced to its simplest ratio (e.g. 100+10 -> 10+1). None when either side
    is missing/zero — a flat discount is never expressed here (see
    ProductDiscPercent / pt_discount_pct, its own separate column)."""
    try:
        buy = int(float(stockreceived)) if stockreceived is not None else 0
        free = int(float(free_qty)) if free_qty is not None else 0
    except (TypeError, ValueError):
        return None
    if buy <= 0 or free <= 0:
        return None
    g = math.gcd(buy, free)
    return f"{buy // g}+{free // g}"


_ASSIGN_COLS = """
    assignment_id, tenant_id, cycle_id, refresh_id, order_item_id, store_id,
    product_code, supplier_code, assigned_qty, assignment_status, remarks,
    export_batch_number, export_split_number, export_uid, exported_at, exported_by,
    received_qty, grn_no, supplier_bill_no, created_by, created_at
"""


# --------------------------------------------------------------------------
# reads (own connection)
# --------------------------------------------------------------------------

def get_assignment(tenant_id, assignment_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_ASSIGN_COLS} "
            "FROM procurement.procurement_order_item_assignments "
            "WHERE tenant_id = ? AND assignment_id = ? AND is_deleted = 0",
            (tenant_id, assignment_id),
        )
        rows = _rows_to_dicts(cursor)
        return _stringify(rows[0]) if rows else None
    finally:
        conn.close()


def list_by_order_item(tenant_id, order_item_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_ASSIGN_COLS} "
            "FROM procurement.procurement_order_item_assignments "
            "WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0 "
            "ORDER BY created_at",
            (tenant_id, order_item_id),
        )
        return [_stringify(r) for r in _rows_to_dicts(cursor)]
    finally:
        conn.close()


def list_by_refresh(tenant_id, refresh_id):
    """Every live assignment for a whole Refresh in one round-trip — powers the
    Supplier Queue build, which previously fanned out one request per assigned
    order item (the N+1 that saturated the backend).

    Enriches each row with real purchase history from sync.PurchaseTrans —
    the actual source of PTR/Cost/MRP/Offer/Discount%, none of which
    procurement_virtual_products ever populates:
      - pt_ptr / pt_cost / pt_mrp / pt_last_purchase_date: THIS row's own
        (product, supplier) pair's most recent purchase (grndate DESC).
      - pt_offer / pt_discount_pct / pt_offer_source_*: the product's overall
        most recent purchase from ANY supplier — offer/discount are a
        property of the last time the product was bought at all, not
        necessarily from the supplier this line is currently assigned to.
        pt_offer_source_supplier_name/date identify that purchase for the
        Export Monitor's hover tooltip when it differs from this line's own
        supplier.
    Also LEFT JOINs procurement.supplier_stock (this exact supplier's real
    scheme/free/discount for this exact product, when a Live Stock import has
    ever mapped it) — a deliberately fresher manual feed, so it still wins
    over the PurchaseTrans-derived offer when present. Defensively guarded —
    supplier_stock may not exist on every deployment, same convention as
    supplier_stock_repository."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT OBJECT_ID('procurement.supplier_stock')")
        has_supplier_stock = cursor.fetchone()[0] is not None
        offer_cols = (
            "ss.scheme AS offer_scheme, ss.free AS offer_free, ss.discount AS offer_discount"
            if has_supplier_stock
            else "CAST(NULL AS INT) AS offer_scheme, CAST(NULL AS INT) AS offer_free, CAST(NULL AS DECIMAL(10,2)) AS offer_discount"
        )
        join_clause = (
            """
            LEFT JOIN procurement.supplier_stock ss
                ON ss.tenant_id = a.tenant_id AND ss.store_id = a.store_id
               AND ss.supplier_code = a.supplier_code AND ss.product_code = a.product_code
            """
            if has_supplier_stock
            else ""
        )
        assign_cols = ", ".join(f"a.{c.strip()}" for c in _ASSIGN_COLS.strip().split(","))
        cursor.execute(
            f"""
            WITH refresh_assignments AS (
                SELECT DISTINCT a.tenant_id, a.store_id, a.product_code, a.supplier_code
                FROM procurement.procurement_order_item_assignments a
                WHERE a.tenant_id = ? AND a.refresh_id = ? AND a.is_deleted = 0
            ),
            supplier_last AS (
                SELECT
                    ra.product_code, ra.supplier_code,
                    pt.purchaseprice AS pt_ptr, pt.itemcost AS pt_cost, pt.mrp AS pt_mrp,
                    pt.grndate AS pt_last_purchase_date,
                    ROW_NUMBER() OVER (
                        PARTITION BY ra.product_code, ra.supplier_code
                        ORDER BY pt.grndate DESC, pt.Grnnumber DESC
                    ) AS rnk
                FROM refresh_assignments ra
                JOIN sync.PurchaseTrans pt
                    ON pt.tenant_id = ra.tenant_id AND pt.store_id = ra.store_id
                   AND pt.ProductCode = TRY_CAST(ra.product_code AS INT)
                   AND pt.SupplierCode = ra.supplier_code
            ),
            overall_last AS (
                SELECT
                    ra.product_code,
                    pt.stockreceived AS pt_stockreceived, pt.FreeQty AS pt_free_qty,
                    pt.ProductDiscPercent AS pt_discount_pct,
                    pt.SupplierCode AS pt_offer_source_code, pt.grndate AS pt_offer_source_date,
                    ROW_NUMBER() OVER (
                        PARTITION BY ra.product_code
                        ORDER BY pt.grndate DESC, pt.Grnnumber DESC
                    ) AS rnk
                FROM (SELECT DISTINCT tenant_id, store_id, product_code FROM refresh_assignments) ra
                JOIN sync.PurchaseTrans pt
                    ON pt.tenant_id = ra.tenant_id AND pt.store_id = ra.store_id
                   AND pt.ProductCode = TRY_CAST(ra.product_code AS INT)
            )
            SELECT {assign_cols}, {offer_cols},
                sl.pt_ptr, sl.pt_cost, sl.pt_mrp, sl.pt_last_purchase_date,
                ol.pt_stockreceived, ol.pt_free_qty, ol.pt_discount_pct, ol.pt_offer_source_date,
                CAST(RTRIM(osup.suppliername) AS VARCHAR(300)) AS pt_offer_source_supplier_name
            FROM procurement.procurement_order_item_assignments a
            {join_clause}
            LEFT JOIN supplier_last sl
                ON sl.product_code = a.product_code AND sl.supplier_code = a.supplier_code AND sl.rnk = 1
            LEFT JOIN overall_last ol
                ON ol.product_code = a.product_code AND ol.rnk = 1
            LEFT JOIN sync.Suppliers osup
                ON osup.tenant_id = a.tenant_id AND osup.store_id = a.store_id
               AND osup.suppliercode = ol.pt_offer_source_code
            WHERE a.tenant_id = ? AND a.refresh_id = ? AND a.is_deleted = 0
            ORDER BY a.order_item_id, a.created_at
            """,
            (tenant_id, refresh_id, tenant_id, refresh_id),
        )
        rows = [_stringify(r) for r in _rows_to_dicts(cursor)]
        for r in rows:
            r["pt_offer"] = _format_offer_ratio(r.pop("pt_stockreceived", None), r.pop("pt_free_qty", None))
        return rows
    finally:
        conn.close()


def list_for_export(tenant_id, assignment_ids):
    """A specific set of assignments (by id) with everything the configurable
    Export Document (Excel/PDF/Image) needs: product_name (from the VPL, via
    the owning order item), sub_location/unit_description (for the sort-by
    option), and the same PurchaseTrans-derived PTR/Cost/MRP/Offer/Discount%
    as list_by_refresh. Deliberately id-scoped rather than refresh-scoped —
    the export dialog already knows exactly which lines the buyer picked."""
    if not assignment_ids:
        return []
    conn = get_connection()
    try:
        cursor = conn.cursor()
        placeholders = ", ".join("?" for _ in assignment_ids)
        cursor.execute(
            f"""
            WITH target AS (
                SELECT assignment_id, tenant_id, store_id, order_item_id,
                       product_code, supplier_code, assigned_qty
                FROM procurement.procurement_order_item_assignments
                WHERE tenant_id = ? AND assignment_id IN ({placeholders}) AND is_deleted = 0
            ),
            prod AS (
                SELECT oi.order_item_id, vp.product_name,
                    COALESCE(NULLIF(RTRIM(vp.sub_location), ''), RTRIM(pr.SubLocation)) AS sub_location,
                    COALESCE(NULLIF(RTRIM(vp.unit_description), ''), RTRIM(pr.UnitDescription)) AS unit_description
                FROM procurement.procurement_order_items oi
                LEFT JOIN procurement.procurement_virtual_products vp
                    ON vp.tenant_id = oi.tenant_id AND vp.refresh_id = oi.refresh_id
                   AND vp.product_id = oi.product_id
                LEFT JOIN sync.Products pr
                    ON pr.tenant_id = oi.tenant_id AND pr.store_id = oi.store_id
                   AND pr.ProductCode = TRY_CAST(oi.product_code AS INT)
                WHERE oi.tenant_id = ? AND oi.order_item_id IN (SELECT order_item_id FROM target)
            ),
            supplier_last AS (
                SELECT
                    t.assignment_id,
                    pt.purchaseprice AS pt_ptr, pt.itemcost AS pt_cost, pt.mrp AS pt_mrp,
                    pt.grndate AS pt_last_purchase_date,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.assignment_id
                        ORDER BY pt.grndate DESC, pt.Grnnumber DESC
                    ) AS rnk
                FROM target t
                JOIN sync.PurchaseTrans pt
                    ON pt.tenant_id = t.tenant_id AND pt.store_id = t.store_id
                   AND pt.ProductCode = TRY_CAST(t.product_code AS INT)
                   AND pt.SupplierCode = t.supplier_code
            ),
            overall_last AS (
                SELECT
                    t.assignment_id,
                    pt.stockreceived AS pt_stockreceived, pt.FreeQty AS pt_free_qty,
                    pt.ProductDiscPercent AS pt_discount_pct,
                    ROW_NUMBER() OVER (
                        PARTITION BY t.assignment_id
                        ORDER BY pt.grndate DESC, pt.Grnnumber DESC
                    ) AS rnk
                FROM target t
                JOIN sync.PurchaseTrans pt
                    ON pt.tenant_id = t.tenant_id AND pt.store_id = t.store_id
                   AND pt.ProductCode = TRY_CAST(t.product_code AS INT)
            )
            SELECT t.assignment_id, t.product_code, t.supplier_code, t.assigned_qty,
                   p.product_name, p.sub_location, p.unit_description,
                   sl.pt_ptr, sl.pt_cost, sl.pt_mrp,
                   ol.pt_stockreceived, ol.pt_free_qty, ol.pt_discount_pct
            FROM target t
            LEFT JOIN prod p ON p.order_item_id = t.order_item_id
            LEFT JOIN supplier_last sl ON sl.assignment_id = t.assignment_id AND sl.rnk = 1
            LEFT JOIN overall_last ol ON ol.assignment_id = t.assignment_id AND ol.rnk = 1
            """,
            (tenant_id, *assignment_ids, tenant_id),
        )
        rows = [_stringify(r) for r in _rows_to_dicts(cursor)]
        for r in rows:
            r["pt_offer"] = _format_offer_ratio(r.pop("pt_stockreceived", None), r.pop("pt_free_qty", None))
        return rows
    finally:
        conn.close()


# --------------------------------------------------------------------------
# transactional checks/writes (caller-owned connection)
# --------------------------------------------------------------------------

def active_assigned_total(conn, tenant_id, order_item_id, exclude_assignment_id=None):
    """SUM of live assigned quantities for an order item."""
    sql = (
        "SELECT COALESCE(SUM(assigned_qty), 0) "
        "FROM procurement.procurement_order_item_assignments "
        "WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0"
    )
    params = [tenant_id, order_item_id]
    if exclude_assignment_id is not None:
        sql += " AND assignment_id <> ?"
        params.append(exclude_assignment_id)
    cursor = conn.cursor()
    cursor.execute(sql, params)
    return cursor.fetchone()[0] or 0


def duplicate_active_exists(conn, tenant_id, order_item_id, supplier_code,
                            exclude_assignment_id=None):
    sql = (
        "SELECT 1 FROM procurement.procurement_order_item_assignments "
        "WHERE tenant_id = ? AND order_item_id = ? AND supplier_code = ? "
        "AND is_deleted = 0"
    )
    params = [tenant_id, order_item_id, supplier_code]
    if exclude_assignment_id is not None:
        sql += " AND assignment_id <> ?"
        params.append(exclude_assignment_id)
    cursor = conn.cursor()
    cursor.execute(sql, params)
    return cursor.fetchone() is not None


def any_active_assignment(conn, tenant_id, order_item_id, exclude_assignment_id=None):
    """The item's single active assignment (any supplier), or None.

    Backs the one-product-one-supplier rule: a working item may carry at most
    one live (non-deleted) assignment regardless of supplier. Returns
    {assignment_id, supplier_code} rather than a bool so the caller can report
    which supplier already owns the product without a second query.
    """
    sql = (
        "SELECT TOP (1) assignment_id, supplier_code "
        "FROM procurement.procurement_order_item_assignments "
        "WHERE tenant_id = ? AND order_item_id = ? AND is_deleted = 0"
    )
    params = [tenant_id, order_item_id]
    if exclude_assignment_id is not None:
        sql += " AND assignment_id <> ?"
        params.append(exclude_assignment_id)
    cursor = conn.cursor()
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return {"assignment_id": str(row[0]), "supplier_code": row[1]} if row else None


def insert_assignment(conn, item, supplier_code, qty, remarks, created_by):
    created_by = _as_uid(created_by)  # NULL for a non-GUID display name
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO procurement.procurement_order_item_assignments
            (tenant_id, cycle_id, refresh_id, order_item_id, store_id,
             product_code, supplier_code, assigned_qty, assignment_status,
             remarks, created_by)
        OUTPUT INSERTED.assignment_id
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)
        """,
        (
            item["tenant_id"], item["cycle_id"], item["refresh_id"],
            item["order_item_id"], item.get("store_id"),
            item.get("product_code"), supplier_code, qty, remarks, created_by,
        ),
    )
    return str(cursor.fetchone()[0])


def update_supplier(conn, tenant_id, assignment_id, supplier_code, updated_by):
    updated_by = _as_uid(updated_by)  # NULL for a non-GUID display name
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_order_item_assignments
        SET supplier_code = ?, updated_by = ?, updated_at = GETDATE()
        WHERE tenant_id = ? AND assignment_id = ? AND is_deleted = 0
        """,
        (supplier_code, updated_by, tenant_id, assignment_id),
    )
    return cursor.rowcount


def update_qty(conn, tenant_id, assignment_id, qty, updated_by):
    updated_by = _as_uid(updated_by)  # NULL for a non-GUID display name
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_order_item_assignments
        SET assigned_qty = ?, updated_by = ?, updated_at = GETDATE()
        WHERE tenant_id = ? AND assignment_id = ? AND is_deleted = 0
        """,
        (qty, updated_by, tenant_id, assignment_id),
    )
    return cursor.rowcount


def soft_delete(conn, tenant_id, assignment_id, deleted_by):
    deleted_by = _as_uid(deleted_by)  # NULL for a non-GUID display name
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE procurement.procurement_order_item_assignments
        SET is_deleted = 1, deleted_at = GETDATE(), deleted_by = ?
        WHERE tenant_id = ? AND assignment_id = ? AND is_deleted = 0
        """,
        (deleted_by, tenant_id, assignment_id),
    )
    return cursor.rowcount


def recompute_order_item(conn, tenant_id, order_item_id):
    """Re-derive assigned_qty / remaining_qty / item_status from live assignments."""
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE oi
        SET assigned_qty = x.total,
            remaining_qty = oi.final_qty - x.total,
            item_status = CASE
                WHEN oi.item_status = 'skipped' THEN 'skipped'
                WHEN x.total <= 0 AND oi.manual_override = 1 THEN 'review'
                WHEN x.total <= 0 THEN 'draft'
                WHEN x.total >= oi.final_qty THEN 'assigned'
                ELSE 'partial' END,
            updated_at = GETDATE()
        FROM procurement.procurement_order_items oi
        CROSS APPLY (
            SELECT COALESCE(SUM(a.assigned_qty), 0) AS total
            FROM procurement.procurement_order_item_assignments a
            WHERE a.order_item_id = oi.order_item_id AND a.is_deleted = 0
        ) x
        WHERE oi.tenant_id = ? AND oi.order_item_id = ? AND oi.is_deleted = 0
        """,
        (tenant_id, order_item_id),
    )
