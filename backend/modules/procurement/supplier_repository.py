"""Data access for the Supplier Queue (Module 4) — real purchase history.

Supplier recommendation ranks candidate suppliers for a product from the
synchronized purchase history NEXORA_PLATFORM.sync.PurchaseTrans, by purchase
frequency then most-recent GRN (the approved ordering). SupplierCode is the
canonical supplier reference (SupplierName is not required). Read-only.
"""

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts as _rows_to_dicts


def top_suppliers(tenant_id, product_code, store_id, limit):
    """Top-N suppliers for a product, ranked by purchase frequency then last GRN."""
    if not store_id or product_code is None:
        return []
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP ({int(limit)})
                a.supplier_code,
                CAST(RTRIM(s.suppliername) AS VARCHAR(300)) AS supplier_name,
                a.purchase_frequency, a.last_grn_date, a.last_grn_no,
                a.last_purchase_rate, a.avg_lead_days
            FROM (
                SELECT
                    CAST(pt.SupplierCode AS VARCHAR(100)) AS supplier_code,
                    COUNT(*)                              AS purchase_frequency,
                    MAX(pt.GRNDate)                       AS last_grn_date,
                    CAST(MAX(pt.GRNNumber) AS VARCHAR(100)) AS last_grn_no,
                    MAX(ISNULL(pt.PurchasePrice, 0))      AS last_purchase_rate,
                    CAST(NULL AS INT)                     AS avg_lead_days
                FROM sync.PurchaseTrans pt
                WHERE pt.tenant_id = ? AND pt.store_id = ?
                  AND CAST(pt.ProductCode AS VARCHAR(100)) = ?
                  AND pt.SupplierCode IS NOT NULL
                GROUP BY pt.SupplierCode
            ) a
            LEFT JOIN sync.Suppliers s
                ON s.tenant_id = ? AND s.store_id = ?
               AND CAST(s.suppliercode AS VARCHAR(100)) = a.supplier_code
            ORDER BY a.purchase_frequency DESC, a.last_grn_date DESC
            """,
            (tenant_id, store_id, str(product_code), tenant_id, store_id),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def top_suppliers_bulk(tenant_id, refresh_id, limit):
    """Top-N suppliers for EVERY working item in a Refresh, in one round-trip.

    Same ranking and source columns as ``top_suppliers`` (purchase frequency,
    then most-recent GRN — the approved ordering), partitioned per order item so
    the Product Grid can render supplier icons for all rows without N calls.
    Read-only.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            WITH ranked AS (
                SELECT
                    CAST(oi.order_item_id AS VARCHAR(100))    AS order_item_id,
                    CAST(oi.product_code AS VARCHAR(100))     AS product_code,
                    oi.store_id                               AS store_id,
                    CAST(pt.SupplierCode AS VARCHAR(100))     AS supplier_code,
                    COUNT(*)                                  AS purchase_frequency,
                    MAX(pt.GRNDate)                           AS last_grn_date,
                    CAST(MAX(pt.GRNNumber) AS VARCHAR(100))   AS last_grn_no,
                    MAX(ISNULL(pt.PurchasePrice, 0))          AS last_purchase_rate,
                    CAST(NULL AS INT)                         AS avg_lead_days,
                    ROW_NUMBER() OVER (
                        PARTITION BY oi.order_item_id
                        ORDER BY COUNT(*) DESC, MAX(pt.GRNDate) DESC
                    ) AS rnk
                FROM procurement.procurement_order_items oi
                JOIN sync.PurchaseTrans pt
                    ON pt.tenant_id = oi.tenant_id
                   AND pt.store_id = oi.store_id
                   AND pt.ProductCode = TRY_CAST(oi.product_code AS INT)
                WHERE oi.tenant_id = ? AND oi.refresh_id = ? AND oi.is_deleted = 0
                  AND pt.SupplierCode IS NOT NULL
                GROUP BY oi.order_item_id, oi.product_code, oi.store_id, pt.SupplierCode
            )
            SELECT r.order_item_id, r.product_code, r.supplier_code,
                   CAST(RTRIM(s.suppliername) AS VARCHAR(300)) AS supplier_name,
                   r.purchase_frequency, r.last_grn_date, r.last_grn_no,
                   r.last_purchase_rate, r.avg_lead_days,
                   ISNULL(s.auto_assign, 1)   AS auto_assign,
                   ISNULL(s.min_products, 2)  AS min_products
            FROM ranked r
            LEFT JOIN sync.Suppliers s
                ON s.tenant_id = ? AND s.store_id = r.store_id
               AND CAST(s.suppliercode AS VARCHAR(100)) = r.supplier_code
            WHERE r.rnk <= ?
            ORDER BY r.order_item_id, r.rnk
            """,
            (tenant_id, refresh_id, tenant_id, int(limit)),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def search_suppliers(tenant_id, store_id, query, limit):
    """Search suppliers seen in the store's purchase history, by code OR name.

    Names come from sync.Suppliers (the supplier master); ranking is by purchase
    frequency from the history.
    """
    if not store_id:
        return []
    q = (query or "").strip()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP ({int(limit)})
                a.supplier_code,
                CAST(RTRIM(s.suppliername) AS VARCHAR(300)) AS supplier_name,
                a.purchase_frequency, a.last_grn_date
            FROM (
                SELECT CAST(pt.SupplierCode AS VARCHAR(100)) AS supplier_code,
                       COUNT(*) AS purchase_frequency, MAX(pt.GRNDate) AS last_grn_date
                FROM sync.PurchaseTrans pt
                WHERE pt.tenant_id = ? AND pt.store_id = ? AND pt.SupplierCode IS NOT NULL
                GROUP BY pt.SupplierCode
            ) a
            LEFT JOIN sync.Suppliers s
                ON s.tenant_id = ? AND s.store_id = ?
               AND CAST(s.suppliercode AS VARCHAR(100)) = a.supplier_code
            WHERE ? = '' OR a.supplier_code LIKE '%' + ? + '%'
                          OR RTRIM(s.suppliername) LIKE '%' + ? + '%'
            ORDER BY a.purchase_frequency DESC
            """,
            (tenant_id, store_id, tenant_id, store_id, q, q, q),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def products_for_supplier(tenant_id, refresh_id, supplier_code):
    """Order-item ids in a Refresh that a supplier has purchase history for
    (Supplier Purchasing mode — 'based on supplier purchase history')."""
    if not supplier_code:
        return []
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Drive from PurchaseTrans by SupplierCode first (IX_PurchaseTrans_Supplier
        # — tenant_id, store_id, SupplierCode, covering ProductCode), matched
        # against the refresh's own (small, already-indexed) order items. Neither
        # side casts pt.ProductCode/pt.SupplierCode — wrapping an indexed column
        # in CAST(...) blocks an index seek regardless of what index exists,
        # which is what made this a full 1M+ row scan (~25s measured) before.
        cursor.execute(
            """
            SELECT DISTINCT CAST(oi.order_item_id AS VARCHAR(100)) AS order_item_id
            FROM procurement.procurement_order_items oi
            JOIN sync.PurchaseTrans pt
                ON pt.tenant_id = oi.tenant_id AND pt.store_id = oi.store_id
               AND pt.ProductCode = TRY_CAST(oi.product_code AS INT)
            WHERE oi.tenant_id = ? AND oi.refresh_id = ? AND oi.is_deleted = 0
              AND pt.SupplierCode = ?
            """,
            (tenant_id, refresh_id, str(supplier_code)),
        )
        return [r["order_item_id"] for r in _rows_to_dicts(cursor)]
    finally:
        conn.close()


def supplier_stats(tenant_id, supplier_code, store_id):
    """Purchase statistics for a supplier from real history."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                CAST(pt.SupplierCode AS VARCHAR(100)) AS supplier_code,
                COUNT(*)                              AS total_purchases,
                COUNT(DISTINCT pt.ProductCode)        AS products_supplied,
                MAX(pt.GRNDate)                       AS last_grn_date,
                CAST(MAX(pt.GRNNumber) AS VARCHAR(100)) AS last_grn_no,
                MAX(ISNULL(pt.PurchasePrice, 0))      AS last_purchase_rate
            FROM sync.PurchaseTrans pt
            WHERE pt.tenant_id = ? AND pt.SupplierCode = ?
              AND (? IS NULL OR pt.store_id = ?)
            GROUP BY pt.SupplierCode
            """,
            (tenant_id, supplier_code, store_id, store_id),
        )
        rows = _rows_to_dicts(cursor)
        return rows[0] if rows else {"supplier_code": supplier_code, "total_purchases": 0}
    finally:
        conn.close()


def list_supplier_settings(tenant_id, store_id):
    """Every supplier for a store with its Auto Assign settings (auto_assign,
    min_products, export_rank) — powers the Supplier Settings panel. Includes
    every supplier in sync.Suppliers for the store, not just ones with
    purchase history in the current refresh, so a buyer can rank ahead of
    time. Ranked suppliers first (ascending), unranked last, then by name."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                CAST(s.suppliercode AS VARCHAR(100))         AS supplier_code,
                CAST(RTRIM(s.suppliername) AS VARCHAR(300))  AS supplier_name,
                ISNULL(s.auto_assign, 1)                     AS auto_assign,
                ISNULL(s.min_products, 2)                    AS min_products,
                s.export_rank                                AS export_rank
            FROM sync.Suppliers s
            WHERE s.tenant_id = ? AND s.store_id = ? AND ISNULL(s.isActive, 1) = 1
            ORDER BY CASE WHEN s.export_rank IS NULL THEN 1 ELSE 0 END, s.export_rank, RTRIM(s.suppliername)
            """,
            (tenant_id, store_id),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def update_supplier_settings(tenant_id, store_id, supplier_code, auto_assign=None, min_products=None, export_rank=None):
    """Partial update of one supplier's Auto Assign settings — only the
    fields the caller actually passed are touched."""
    sets = []
    params = []
    if auto_assign is not None:
        sets.append("auto_assign = ?")
        params.append(1 if auto_assign else 0)
    if min_products is not None:
        sets.append("min_products = ?")
        params.append(min_products)
    if export_rank is not None:
        # 0/negative clears the rank back to "unranked" — ranks are 1..N.
        sets.append("export_rank = ?")
        params.append(export_rank if export_rank > 0 else None)
    if not sets:
        return
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE sync.Suppliers SET {', '.join(sets)} "
            "WHERE tenant_id = ? AND store_id = ? AND suppliercode = ?",
            (*params, tenant_id, store_id, supplier_code),
        )
        conn.commit()
    finally:
        conn.close()
