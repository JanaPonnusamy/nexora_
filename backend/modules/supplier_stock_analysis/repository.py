"""Platform-only data access for Supplier Stock Analysis."""

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts


def _object_exists(cur, name):
    cur.execute("SELECT OBJECT_ID(?)", (name,))
    row = cur.fetchone()
    return bool(row and row[0])


def _fetch(sql, params=()):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return rows_to_dicts(cur)
    finally:
        conn.close()


def list_suppliers(tenant_id, store_id=None, search=""):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if not _object_exists(cur, "procurement.supplier_stock"):
            return []
        store_clause = "AND ss.store_id = ?" if store_id else ""
        params = [tenant_id]
        if store_id:
            params.append(store_id)
        term = (search or "").strip()
        params.extend([term, term, term])
        cur.execute(
            f"""
            SELECT
                CAST(ss.supplier_code AS VARCHAR(100)) AS supplier_code,
                COALESCE(MAX(NULLIF(s.suppliername, '')), '') AS supplier_name,
                COUNT(1) AS product_count,
                SUM(CASE WHEN ISNULL(ss.available_stock, 0) > 0 THEN 1 ELSE 0 END) AS available_count,
                SUM(ISNULL(ss.available_stock, 0)) AS total_available_stock,
                MAX(ss.imported_at) AS last_imported_at
            FROM procurement.supplier_stock ss
            LEFT JOIN sync.Suppliers s
                ON s.tenant_id = ss.tenant_id
               AND s.store_id = ss.store_id
               AND CAST(s.suppliercode AS VARCHAR(100)) = CAST(ss.supplier_code AS VARCHAR(100))
            WHERE ss.tenant_id = ?
              {store_clause}
              AND ss.is_active = 1
              AND (? = ''
                   OR CAST(ss.supplier_code AS VARCHAR(100)) LIKE ? + '%'
                   OR s.suppliername LIKE '%' + ? + '%')
            GROUP BY ss.supplier_code
            ORDER BY supplier_name, ss.supplier_code
            """,
            tuple(params),
        )
        return rows_to_dicts(cur)
    finally:
        conn.close()


def list_supplier_products(tenant_id, supplier_code, store_id=None, search="", only_available=True):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if not _object_exists(cur, "procurement.supplier_stock"):
            return []
        store_clause = "AND ss.store_id = ?" if store_id else ""
        params = [tenant_id, supplier_code]
        if store_id:
            params.append(store_id)
        term = (search or "").strip()
        params.extend([1 if only_available else 0, term, term, term, term])
        cur.execute(
            f"""
            SELECT TOP 500
                CAST(ss.supplier_stock_id AS VARCHAR(36)) AS supplier_stock_id,
                CAST(ss.tenant_id AS VARCHAR(36)) AS tenant_id,
                CAST(ss.store_id AS VARCHAR(36)) AS store_id,
                st.store_code,
                st.store_name,
                CAST(ss.supplier_code AS VARCHAR(100)) AS supplier_code,
                CAST(ss.supplier_product_code AS VARCHAR(100)) AS supplier_product_code,
                ss.supplier_product_name,
                CAST(ss.product_code AS VARCHAR(100)) AS product_code,
                p.productname AS mapped_product_name,
                ss.available_stock,
                ss.ptr,
                ss.mrp,
                ss.discount,
                ss.packing,
                ss.free,
                ss.minimum_qty,
                ss.scheme,
                ss.transaction_date,
                ss.source,
                ss.imported_at,
                CASE WHEN ss.product_code IS NULL THEN 0 ELSE 1 END AS has_mapping
            FROM procurement.supplier_stock ss
            LEFT JOIN dbo.stores st ON st.tenant_id = ss.tenant_id AND st.store_id = ss.store_id
            LEFT JOIN sync.Products p
                ON p.tenant_id = ss.tenant_id
               AND p.store_id = ss.store_id
               AND CAST(p.productcode AS VARCHAR(100)) = CAST(ss.product_code AS VARCHAR(100))
            WHERE ss.tenant_id = ?
              AND CAST(ss.supplier_code AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
              {store_clause}
              AND ss.is_active = 1
              AND (? = 0 OR ISNULL(ss.available_stock, 0) > 0)
              AND (? = ''
                   OR ss.supplier_product_name LIKE '%' + ? + '%'
                   OR CAST(ss.supplier_product_code AS VARCHAR(100)) LIKE ? + '%'
                   OR CAST(ss.product_code AS VARCHAR(100)) LIKE ? + '%')
            ORDER BY ss.supplier_product_name
            """,
            tuple(params),
        )
        return rows_to_dicts(cur)
    finally:
        conn.close()


def supplier_stock_row(supplier_stock_id, tenant_id=None):
    params = [supplier_stock_id]
    tenant_clause = ""
    if tenant_id:
        tenant_clause = "AND tenant_id = ?"
        params.append(tenant_id)
    rows = _fetch(
        f"""
        SELECT TOP 1
            CAST(supplier_stock_id AS VARCHAR(36)) AS supplier_stock_id,
            CAST(tenant_id AS VARCHAR(36)) AS tenant_id,
            CAST(store_id AS VARCHAR(36)) AS store_id,
            CAST(supplier_code AS VARCHAR(100)) AS supplier_code,
            CAST(supplier_product_code AS VARCHAR(100)) AS supplier_product_code,
            supplier_product_name,
            CAST(product_code AS VARCHAR(100)) AS product_code,
            available_stock, ptr, mrp, discount, packing, free, minimum_qty, scheme
        FROM procurement.supplier_stock
        WHERE supplier_stock_id = ?
          {tenant_clause}
          AND is_active = 1
        """,
        tuple(params),
    )
    return rows[0] if rows else None


def exact_mapping(tenant_id, store_id, supplier_code, supplier_product_code):
    rows = _fetch(
        """
        SELECT TOP 1
            CAST(spm.store_id AS VARCHAR(36)) AS store_id,
            CAST(spm.tenant_id AS VARCHAR(36)) AS tenant_id,
            CAST(spm.SupplierCode AS VARCHAR(100)) AS supplier_code,
            CAST(spm.SupplierProductCode AS VARCHAR(100)) AS supplier_product_code,
            spm.SupplierProductName AS supplier_product_name,
            CAST(spm.ProductCode AS VARCHAR(100)) AS product_code,
            p.productname AS product_name,
            spm.UserName AS username,
            spm.LastModifiedDate AS last_modified_date
        FROM sync.SupplierProductMatch spm
        LEFT JOIN sync.Products p
            ON p.tenant_id = spm.tenant_id
           AND p.store_id = spm.store_id
           AND CAST(p.productcode AS VARCHAR(100)) = CAST(spm.ProductCode AS VARCHAR(100))
        WHERE spm.tenant_id = ?
          AND spm.store_id = ?
          AND CAST(spm.SupplierCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
          AND CAST(spm.SupplierProductCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
          AND ISNULL(spm.IsActive, 1) = 1
        """,
        (tenant_id, store_id, supplier_code, supplier_product_code),
    )
    return rows[0] if rows else None


def suggestions(tenant_id, supplier_product_name, store_id=None, limit=25):
    tokens = [
        t.strip("'\"").strip()
        for t in (supplier_product_name or "").replace("@", " ").replace("/", " ").split()
    ]
    tokens = [t for t in tokens if len(t) >= 3][:4]
    if not tokens:
        return []
    where = ["p.tenant_id = ?", "p.isactive = 1"]
    params = [tenant_id]
    if store_id:
        where.append("p.store_id = ?")
        params.append(store_id)
    score = []
    score_params = []
    match_clauses = []
    match_params = []
    for token in tokens:
        score.append("CASE WHEN p.productname LIKE '%' + ? + '%' THEN 1 ELSE 0 END")
        score_params.append(token)
        match_clauses.append("p.productname LIKE '%' + ? + '%'")
        match_params.append(token)
    # A product only needs to match at least one token (OR) to surface as a candidate;
    # match_score then ranks by how many tokens it actually matched.
    where.append("(" + " OR ".join(match_clauses) + ")")
    params = [limit] + score_params + params + match_params
    return _fetch(
        f"""
        SELECT TOP (?)
            CAST(p.store_id AS VARCHAR(36)) AS store_id,
            st.store_code,
            st.store_name,
            CAST(p.productcode AS VARCHAR(100)) AS product_code,
            p.productname AS product_name,
            p.totalstock AS stock,
            p.mrp,
            ({' + '.join(score)}) AS match_score
        FROM sync.Products p
        LEFT JOIN dbo.stores st ON st.tenant_id = p.tenant_id AND st.store_id = p.store_id
        WHERE {' AND '.join(where)}
        ORDER BY match_score DESC, p.productname
        """,
        tuple(params),
    )


def all_store_stock(tenant_id, product_code):
    return _fetch(
        """
        SELECT
            CAST(st.store_id AS VARCHAR(36)) AS store_id,
            st.store_code,
            st.store_name,
            CAST(p.productcode AS VARCHAR(100)) AS product_code,
            p.productname AS product_name,
            ISNULL(p.totalstock, 0) AS total_stock,
            p.saleunit AS sale_unit,
            p.unitdescription AS unit_description,
            p.mrp,
            p.purchaseprice AS ptr,
            MAX(b.grndate) AS last_grn_date,
            MAX(b.lastsaledate) AS last_sale_date
        FROM dbo.stores st
        LEFT JOIN sync.Products p
            ON p.tenant_id = st.tenant_id
           AND p.store_id = st.store_id
           AND CAST(p.productcode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
           AND p.isactive = 1
        LEFT JOIN sync.Batches b
            ON b.tenant_id = st.tenant_id
           AND b.store_id = st.store_id
           AND CAST(b.productcode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
        WHERE st.tenant_id = ?
          AND ISNULL(st.is_active, 1) = 1
        GROUP BY st.store_id, st.store_code, st.store_name, p.productcode,
                 p.productname, p.totalstock, p.saleunit, p.unitdescription,
                 p.mrp, p.purchaseprice
        ORDER BY st.store_name
        """,
        (product_code, product_code, tenant_id),
    )


def batches_all_stores(tenant_id, product_code):
    return _fetch(
        """
        SELECT TOP 100
            CAST(b.store_id AS VARCHAR(36)) AS store_id,
            st.store_code,
            st.store_name,
            CAST(b.productcode AS VARCHAR(100)) AS product_code,
            b.batchcode,
            b.stock,
            b.mrp,
            b.expirydate,
            b.itemcost,
            b.purchaseprice AS ptr,
            b.grndate,
            b.lastsaledate
        FROM sync.Batches b
        LEFT JOIN dbo.stores st ON st.tenant_id = b.tenant_id AND st.store_id = b.store_id
        WHERE b.tenant_id = ?
          AND CAST(b.productcode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
          AND ISNULL(b.stock, 0) >= 0
        ORDER BY st.store_name, b.grndate DESC
        """,
        (tenant_id, product_code),
    )


def purchase_history_all_stores(tenant_id, product_code):
    return _fetch(
        """
        SELECT TOP 100
            CAST(pt.store_id AS VARCHAR(36)) AS store_id,
            st.store_code,
            st.store_name,
            pt.Grnnumber AS grn_no,
            pt.stockreceived AS qty,
            pt.FreeQty AS free,
            pt.ProductDiscPercent AS discount,
            pt.itemcost,
            pt.purchaseprice AS ptr,
            pt.mrp,
            pt.grndate,
            COALESCE(s.suppliername, CAST(pt.SupplierCode AS NVARCHAR(100))) AS supplier
        FROM sync.PurchaseTrans pt
        LEFT JOIN dbo.stores st ON st.tenant_id = pt.tenant_id AND st.store_id = pt.store_id
        LEFT JOIN sync.Suppliers s
            ON s.tenant_id = pt.tenant_id
           AND s.store_id = pt.store_id
           AND CAST(s.suppliercode AS VARCHAR(100)) = CAST(pt.SupplierCode AS VARCHAR(100))
        WHERE pt.tenant_id = ?
          AND CAST(pt.ProductCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
        ORDER BY pt.grndate DESC
        """,
        (tenant_id, product_code),
    )


def sales_history_all_stores(tenant_id, product_code):
    return _fetch(
        """
        SELECT TOP 100
            CAST(psi.store_id AS VARCHAR(36)) AS store_id,
            st.store_code,
            st.store_name,
            psi.BillNumber AS bill_no,
            si.BillDate AS bill_date,
            SUM(psi.quantity) AS qty,
            MAX(psi.DiscountPercentage) AS discount,
            psi.Seriesname AS bill_type,
            psi.mrp,
            psi.purchaseprice AS ptr,
            si.CUSTOMERNAME AS customer_name
        FROM sync.ProductSaleInformation psi
        LEFT JOIN dbo.stores st ON st.tenant_id = psi.tenant_id AND st.store_id = psi.store_id
        LEFT JOIN sync.SaleInformation si
            ON si.tenant_id = psi.tenant_id
           AND si.store_id = psi.store_id
           AND si.billnumber = psi.BillNumber
        WHERE psi.tenant_id = ?
          AND CAST(psi.ProductCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
          AND ISNULL(psi.transactionvalidity, 0) = 0
        GROUP BY psi.store_id, st.store_code, st.store_name, psi.BillNumber,
                 si.BillDate, psi.Seriesname, psi.mrp, psi.purchaseprice, si.CUSTOMERNAME
        ORDER BY si.BillDate DESC
        """,
        (tenant_id, product_code),
    )


def monthly_movement_all_stores(tenant_id, product_code, months=6):
    return _fetch(
        """
        SELECT
            CAST(pt.store_id AS VARCHAR(36)) AS store_id,
            st.store_code,
            st.store_name,
            CONVERT(VARCHAR(7), pt.MonthOfStatistics, 120) AS month,
            SUM(ISNULL(pt.StockInHand, 0)) AS stock,
            SUM(ISNULL(pt.PurchaseQuantity, 0)) AS purchase_qty,
            SUM(ISNULL(pt.TransferInQuantity, 0)) AS transfer_in_qty,
            SUM(ISNULL(pt.SaleQuantity, 0)) AS sale_qty,
            SUM(ISNULL(pt.TransferOutQuantity, 0)) AS transfer_out_qty,
            SUM(ISNULL(pt.AdjustmentQuantity, 0)) AS adjustment_qty
        FROM sync.ProductTrans pt
        LEFT JOIN dbo.stores st ON st.tenant_id = pt.tenant_id AND st.store_id = pt.store_id
        WHERE pt.tenant_id = ?
          AND CAST(pt.ProductCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
          AND pt.MonthOfStatistics >= DATEADD(MONTH, -?, GETDATE())
        GROUP BY pt.store_id, st.store_code, st.store_name, CONVERT(VARCHAR(7), pt.MonthOfStatistics, 120)
        ORDER BY st.store_name, month
        """,
        (tenant_id, product_code, months),
    )


def upsert_mapping(payload):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            IF EXISTS (
                SELECT 1 FROM sync.SupplierProductMatch
                WHERE tenant_id = ? AND store_id = ?
                  AND CAST(SupplierCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
                  AND CAST(SupplierProductCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
            )
                UPDATE sync.SupplierProductMatch
                   SET SupplierProductName = ?,
                       ProductCode = ?,
                       UserName = ?,
                       LastModifiedDate = GETDATE(),
                       IsActive = 1
                 WHERE tenant_id = ? AND store_id = ?
                   AND CAST(SupplierCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
                   AND CAST(SupplierProductCode AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
            ELSE
                INSERT INTO sync.SupplierProductMatch
                    (store_id, tenant_id, SupplierCode, SupplierProductCode,
                     SupplierProductName, ProductCode, UserName, LastModifiedDate, IsActive)
                VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE(), 1)

            UPDATE procurement.supplier_stock
               SET product_code = ?
             WHERE tenant_id = ?
               AND store_id = ?
               AND CAST(supplier_code AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
               AND CAST(supplier_product_code AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
               AND is_active = 1
            """,
            (
                payload["tenant_id"], payload["store_id"], payload["supplier_code"], payload["supplier_product_code"],
                payload.get("supplier_product_name"), payload["product_code"], payload.get("username"),
                payload["tenant_id"], payload["store_id"], payload["supplier_code"], payload["supplier_product_code"],
                payload["store_id"], payload["tenant_id"], payload["supplier_code"], payload["supplier_product_code"],
                payload.get("supplier_product_name"), payload["product_code"], payload.get("username"),
                payload["product_code"], payload["tenant_id"], payload["store_id"],
                payload["supplier_code"], payload["supplier_product_code"],
            ),
        )
        conn.commit()
        return {"success": True}
    finally:
        conn.close()


def replace_supplier_stock(tenant_id, store_id, supplier_code, rows, imported_by):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE procurement.supplier_stock
               SET is_active = 0
             WHERE tenant_id = ? AND store_id = ? AND supplier_code = ? AND source = 'excel'
            """,
            (tenant_id, store_id, supplier_code),
        )
        if rows:
            cur.fast_executemany = True
            cur.executemany(
                """
                INSERT INTO procurement.supplier_stock
                    (tenant_id, store_id, supplier_code, supplier_product_code,
                     supplier_product_name, available_stock, ptr, mrp, discount,
                     packing, free, minimum_qty, scheme, transaction_date, source,
                     is_active, imported_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'excel', 1, ?)
                """,
                [
                    (
                        tenant_id, store_id, supplier_code,
                        r.get("supplier_product_code"), r.get("supplier_product_name"),
                        r.get("available_stock"), r.get("ptr"), r.get("mrp"),
                        r.get("discount"), r.get("packing"), r.get("free"),
                        r.get("minimum_qty"), r.get("scheme"), r.get("transaction_date"),
                        imported_by,
                    )
                    for r in rows
                ],
            )
        cur.execute(
            """
            UPDATE ss
               SET ss.product_code = CAST(spm.ProductCode AS VARCHAR(50))
            FROM procurement.supplier_stock ss
            JOIN sync.SupplierProductMatch spm
              ON spm.tenant_id = ss.tenant_id
             AND spm.store_id = ss.store_id
             AND CAST(spm.SupplierCode AS VARCHAR(100)) = CAST(ss.supplier_code AS VARCHAR(100))
             AND CAST(spm.SupplierProductCode AS VARCHAR(100)) = CAST(ss.supplier_product_code AS VARCHAR(100))
             AND ISNULL(spm.IsActive, 1) = 1
            WHERE ss.tenant_id = ?
              AND ss.store_id = ?
              AND CAST(ss.supplier_code AS VARCHAR(100)) = CAST(? AS VARCHAR(100))
              AND ss.source = 'excel'
              AND ss.is_active = 1
            """,
            (tenant_id, store_id, supplier_code),
        )
        resolved = cur.rowcount
        conn.commit()
        return {"imported": len(rows), "product_codes_resolved": resolved}
    finally:
        conn.close()

