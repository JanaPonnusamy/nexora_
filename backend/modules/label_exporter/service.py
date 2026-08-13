"""Label Exporter service layer.

Queries the synced store stock tables (via the platform DB) and returns
product/box/batch data for the label-printing workflow.
"""

from config.database import get_connection


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
    """Search products for label assignment."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        where_clauses = ["p.tenant_id = ?", "p.store_id = ?"]
        params: list = [tenant_id, store_id]

        if q:
            where_clauses.append("p.product_name LIKE ?")
            params.append(f"%{q}%")
        if starts_with:
            where_clauses.append("p.product_name LIKE ?")
            params.append(f"{starts_with}%")
        if unit_description:
            where_clauses.append("p.unit_description = ?")
            params.append(unit_description)
        if box_number:
            where_clauses.append("p.box_number = ?")
            params.append(box_number)
        if stock_filter == "in_stock":
            where_clauses.append("p.total_stock > 0")
        elif stock_filter == "zero_recent_sale":
            where_clauses.append("(p.total_stock = 0 OR p.sale_days IS NULL)")
        if int(only_null_sublocation):
            where_clauses.append("p.sublocation IS NULL")
        if int(only_sale_unit_gt_one):
            where_clauses.append("p.sale_unit_qty > 1")

        where_sql = " AND ".join(where_clauses)
        sql = f"""
            SELECT TOP 200
                p.product_code, p.product_name, p.unit_description,
                p.box_number, p.mrp, p.total_stock,
                p.sale_days, p.purchase_days
            FROM dbo.store_product_summary p
            WHERE {where_sql}
            ORDER BY p.product_name
        """
        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

        # Collect distinct unit_description values
        unit_desc_sql = f"""
            SELECT DISTINCT p.unit_description
            FROM dbo.store_product_summary p
            WHERE {where_sql} AND p.unit_description IS NOT NULL
            ORDER BY p.unit_description
        """
        cursor.execute(unit_desc_sql, params)
        unit_descriptions = [r[0] for r in cursor.fetchall()]

        # Last box for letter
        last_box = None
        if starts_with:
            box_sql = """
                SELECT TOP 1 p.box_number
                FROM dbo.store_product_summary p
                WHERE p.tenant_id = ? AND p.store_id = ?
                  AND p.box_number LIKE ?
                ORDER BY p.box_number DESC
            """
            cursor.execute(box_sql, [tenant_id, store_id, f"{starts_with}%"])
            box_row = cursor.fetchone()
            if box_row:
                last_box = box_row[0]

        return {
            "rows": rows,
            "unit_descriptions": unit_descriptions,
            "last_box_for_letter": last_box,
        }
    finally:
        conn.close()


def search_boxes(tenant_id: str, store_id: str, q: str = "", starts_with: str = ""):
    """Search boxes in a store."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        where_clauses = ["p.tenant_id = ?", "p.store_id = ?", "p.box_number IS NOT NULL"]
        params: list = [tenant_id, store_id]

        if q:
            where_clauses.append("p.box_number = ?")
            params.append(q)
        if starts_with:
            where_clauses.append("p.box_number LIKE ?")
            params.append(f"{starts_with}%")

        where_sql = " AND ".join(where_clauses)
        sql = f"""
            SELECT
                p.box_number,
                COUNT(*) AS product_count,
                SUM(p.total_stock) AS total_stock,
                MAX(p.sale_days) AS best_sale_days,
                MAX(p.purchase_days) AS best_purchase_days
            FROM dbo.store_product_summary p
            WHERE {where_sql}
            GROUP BY p.box_number
            ORDER BY p.box_number
        """
        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        boxes = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return {"boxes": boxes}
    finally:
        conn.close()


def get_box_products(tenant_id: str, store_id: str, box_number: str):
    """Get all products in a specific box."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        sql = """
            SELECT
                p.product_code, p.product_name, p.unit_description,
                p.mrp, p.total_stock, p.sale_days, p.purchase_days
            FROM dbo.store_product_summary p
            WHERE p.tenant_id = ? AND p.store_id = ? AND p.box_number = ?
            ORDER BY p.product_name
        """
        cursor.execute(sql, [tenant_id, store_id, box_number])
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return {"rows": rows}
    finally:
        conn.close()


def get_product_batches(tenant_id: str, store_id: str, product_code: str):
    """Get batch-level detail for a product."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        sql = """
            SELECT
                b.product_code, b.batch_code, b.stock,
                b.expiry_date, b.mrp, b.sale_days, b.purchase_days,
                CASE WHEN b.expiry_date < GETDATE() THEN 1 ELSE 0 END AS is_expired
            FROM dbo.store_batch_summary b
            WHERE b.tenant_id = ? AND b.store_id = ? AND b.product_code = ?
            ORDER BY b.expiry_date
        """
        cursor.execute(sql, [tenant_id, store_id, product_code])
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        for row in rows:
            row["is_expired"] = bool(row.get("is_expired", 0))
        return {"rows": rows}
    finally:
        conn.close()
