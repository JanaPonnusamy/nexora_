"""Data access for the Supplier Order Optimization Engine.

The optimization stage sits after Auto Supplier Assignment and before Export.
It works entirely on the *draft* (not-yet-exported) assignments of a Refresh,
which are loaded in a small number of batched queries (Performance §11 — no
per-supplier or per-product round-trips):

  * load_draft_assignments  — every movable draft assignment + its purchase
    value basis (Final-Qty × PTR, the same basis the Supplier Queue shows).
  * list_min_orders         — the configured Minimum Order Value per supplier.
  * load_live_stock_map     — (supplier, product) -> available stock, when the
    supplier live-stock table is provisioned.

Candidate suppliers for each product (who else supplies it, at what last rate)
are read through the existing supplier_repository.top_suppliers_bulk — no new
purchase-history query is introduced.

Writes: upsert a supplier's Minimum Order Value, and append one audit row per
product moved between suppliers (procurement.optimization_moves).
"""

import os

from config.database import get_connection
from modules.procurement._dbutil import (
    as_uid as _as_uid,
    rows_to_dicts as _rows_to_dicts,
    stringify as _stringify,
)

_SQL_DIR = os.path.join(os.path.dirname(__file__), "sql")
_DDL_FILE = os.path.join(_SQL_DIR, "0012_supplier_optimization.sql")

_schema_ready = False


def ensure_schema():
    """Create supplier_min_order + optimization_moves if absent (idempotent).

    Mirrors the supplier-stock provisioning pattern (splits the DDL on GO) so a
    fresh environment self-provisions on first use — no manual migration step.
    """
    global _schema_ready
    if _schema_ready:
        return
    with open(_DDL_FILE, "r", encoding="utf-8") as fh:
        script = fh.read()
    batches = [b.strip() for b in script.split("\nGO") if b.strip()]
    conn = get_connection()
    try:
        cur = conn.cursor()
        for batch in batches:
            cur.execute(batch)
        conn.commit()
    finally:
        conn.close()
    _schema_ready = True


# --------------------------------------------------------------------------
# Minimum Order Value (per tenant/store/supplier)
# --------------------------------------------------------------------------

def list_min_orders(tenant_id, store_id):
    """Configured Minimum Order Value per supplier -> {supplier_code: value}."""
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT CAST(supplier_code AS VARCHAR(100)) AS supplier_code,
                   min_order_value
            FROM procurement.supplier_min_order
            WHERE tenant_id = ? AND store_id = ?
            """,
            (tenant_id, store_id),
        )
        return {r["supplier_code"]: float(r["min_order_value"] or 0)
                for r in _rows_to_dicts(cur)}
    finally:
        conn.close()


def upsert_min_order(tenant_id, store_id, supplier_code, value, updated_by):
    """Set (or clear) a supplier's Minimum Order Value for a store."""
    ensure_schema()
    updated_by = _as_uid(updated_by)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            MERGE procurement.supplier_min_order AS t
            USING (SELECT ? AS tenant_id, ? AS store_id, ? AS supplier_code) AS s
              ON  t.tenant_id = s.tenant_id
              AND t.store_id = s.store_id
              AND t.supplier_code = s.supplier_code
            WHEN MATCHED THEN
              UPDATE SET min_order_value = ?, updated_by = ?, updated_at = GETDATE()
            WHEN NOT MATCHED THEN
              INSERT (tenant_id, store_id, supplier_code, min_order_value, updated_by)
              VALUES (s.tenant_id, s.store_id, s.supplier_code, ?, ?);
            """,
            (tenant_id, store_id, supplier_code,
             value, updated_by, value, updated_by),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Batched read of the movable draft assignments
# --------------------------------------------------------------------------

def load_draft_assignments(tenant_id, refresh_id):
    """Every non-exported draft assignment in the Refresh, with the purchase
    value basis (PTR = Last Purchase Rate, falling back to VPL PTR cost) — the
    same basis the Supplier Queue uses so money numbers match across panels.

    One query. Exported / deleted assignments and skipped items are excluded
    (they are locked out of optimization)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                CAST(a.assignment_id AS VARCHAR(100))  AS assignment_id,
                CAST(a.order_item_id AS VARCHAR(100))  AS order_item_id,
                CAST(a.supplier_code AS VARCHAR(100))  AS supplier_code,
                CAST(a.product_code AS VARCHAR(100))   AS product_code,
                a.assigned_qty                         AS assigned_qty,
                CAST(a.store_id AS VARCHAR(100))       AS store_id,
                CAST(a.cycle_id AS VARCHAR(100))       AS cycle_id,
                oi.item_status                         AS item_status,
                oi.manual_override                     AS manual_override,
                vp.product_name                        AS product_name,
                vp.mrp                                 AS mrp,
                COALESCE(vp.last_purchase_rate, vp.ptr_cost, 0) AS ptr
            FROM procurement.procurement_order_item_assignments a
            JOIN procurement.procurement_order_items oi
                ON oi.order_item_id = a.order_item_id AND oi.is_deleted = 0
            LEFT JOIN procurement.procurement_virtual_products vp
                ON vp.tenant_id = oi.tenant_id
               AND vp.refresh_id = oi.refresh_id
               AND vp.product_id = oi.product_id
            WHERE a.tenant_id = ? AND a.refresh_id = ?
              AND a.is_deleted = 0
              AND a.assignment_status = 'draft'
              AND oi.item_status <> 'skipped'
            """,
            (tenant_id, refresh_id),
        )
        rows = _rows_to_dicts(cur)
        for r in rows:
            r["assigned_qty"] = float(r["assigned_qty"] or 0)
            r["ptr"] = float(r["ptr"] or 0)
            r["mrp"] = float(r["mrp"]) if r["mrp"] is not None else None
        return rows
    finally:
        conn.close()


def load_live_stock_map(tenant_id, refresh_id, store_id):
    """(supplier_code, product_code) -> available_stock for the Refresh's store.

    Returns {} when the supplier-stock table is not provisioned or no store is
    known — the caller then treats live-stock gating as disabled."""
    if not store_id:
        return {}
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT OBJECT_ID('procurement.supplier_stock')")
        if cur.fetchone()[0] is None:
            return {}
        cur.execute(
            """
            SELECT CAST(ss.supplier_code AS VARCHAR(100)) AS supplier_code,
                   CAST(ss.product_code AS VARCHAR(100))  AS product_code,
                   SUM(ISNULL(ss.available_stock, 0))     AS available_stock
            FROM procurement.supplier_stock ss
            WHERE ss.tenant_id = ? AND ss.store_id = ? AND ss.is_active = 1
              AND ss.product_code IS NOT NULL
            GROUP BY ss.supplier_code, ss.product_code
            """,
            (tenant_id, store_id),
        )
        return {(r["supplier_code"], r["product_code"]): float(r["available_stock"] or 0)
                for r in _rows_to_dicts(cur)}
    finally:
        conn.close()


def supplies_product(tenant_id, store_id, product_code, supplier_code):
    """True when the supplier is a valid source for the product — either they
    have purchase history for it (sync.PurchaseTrans) or live stock for it
    (procurement.supplier_stock). Used to gate Manual Move (§8) and to
    re-validate a suggestion at apply time."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 1 WHERE EXISTS (
                SELECT 1 FROM sync.PurchaseTrans pt
                WHERE pt.tenant_id = ? AND pt.store_id = ?
                  AND CAST(pt.ProductCode AS VARCHAR(100)) = ?
                  AND CAST(pt.SupplierCode AS VARCHAR(100)) = ?
            )
            """,
            (tenant_id, store_id, str(product_code), str(supplier_code)),
        )
        if cur.fetchone() is not None:
            return True
        if _object_id(cur, "procurement.supplier_stock"):
            cur.execute(
                """
                SELECT 1 WHERE EXISTS (
                    SELECT 1 FROM procurement.supplier_stock ss
                    WHERE ss.tenant_id = ? AND ss.store_id = ? AND ss.is_active = 1
                      AND CAST(ss.product_code AS VARCHAR(100)) = ?
                      AND CAST(ss.supplier_code AS VARCHAR(100)) = ?
                )
                """,
                (tenant_id, store_id, str(product_code), str(supplier_code)),
            )
            if cur.fetchone() is not None:
                return True
        return False
    finally:
        conn.close()


def _object_id(cur, name):
    cur.execute("SELECT OBJECT_ID(?)", (name,))
    return cur.fetchone()[0] is not None


def get_assignment_row(conn, tenant_id, assignment_id):
    """Minimal assignment read on a caller-owned connection (for a move txn)."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT CAST(a.assignment_id AS VARCHAR(100)) AS assignment_id,
               CAST(a.order_item_id AS VARCHAR(100)) AS order_item_id,
               CAST(a.supplier_code AS VARCHAR(100)) AS supplier_code,
               CAST(a.product_code AS VARCHAR(100))  AS product_code,
               a.assigned_qty                        AS assigned_qty,
               a.assignment_status                   AS assignment_status,
               CAST(a.store_id AS VARCHAR(100))       AS store_id,
               CAST(a.cycle_id AS VARCHAR(100))       AS cycle_id
        FROM procurement.procurement_order_item_assignments a
        WHERE a.tenant_id = ? AND a.assignment_id = ? AND a.is_deleted = 0
        """,
        (tenant_id, assignment_id),
    )
    rows = _rows_to_dicts(cur)
    return rows[0] if rows else None


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------

def insert_move(conn, *, tenant_id, cycle_id, refresh_id, store_id, order_item_id,
                assignment_id, product_code, from_supplier, to_supplier,
                moved_qty, moved_value, reason, moved_by):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO procurement.optimization_moves
            (tenant_id, cycle_id, refresh_id, store_id, order_item_id, assignment_id,
             product_code, from_supplier, to_supplier, moved_qty, moved_value,
             reason, moved_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (tenant_id, _as_uid(cycle_id), refresh_id, _as_uid(store_id),
         order_item_id, assignment_id, product_code, from_supplier, to_supplier,
         moved_qty, moved_value, reason, _as_uid(moved_by)),
    )


def list_moves(tenant_id, refresh_id):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT move_id, order_item_id, assignment_id, product_code,
                   from_supplier, to_supplier, moved_qty, moved_value,
                   reason, moved_by, moved_at
            FROM procurement.optimization_moves
            WHERE tenant_id = ? AND refresh_id = ?
            ORDER BY moved_at DESC
            """,
            (tenant_id, refresh_id),
        )
        return [_stringify(r) for r in _rows_to_dicts(cur)]
    finally:
        conn.close()
