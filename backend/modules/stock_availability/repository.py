"""Read-only data access for the Stock Availability module.

Every query targets NEXORA_PLATFORM only. Business data lives in the synced
`sync.[<Table>]` tables (stamped with tenant_id / store_id during sync); store
metadata lives in `dbo.stores`. All business logic is kept inside stored
procedures (stock.usp_*), adapted from the proven legacy OrderNMC procedures.
This layer just invokes them and shapes the rows into dictionaries.
"""

from config.database import get_connection


def _run_sp(sql, params):
    """Execute a stored procedure and return rows as a list of dicts.

    Returns [] when the procedure yields no result set. Read-only: no commit.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        if not cursor.description:
            return []
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def _fetch(sql, params=()):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        if not cursor.description:
            return []
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def _execute(sql, params=()):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        conn.commit()
        return cursor.rowcount
    finally:
        cursor.close()
        conn.close()


def _rows_from_cursor(cursor):
    if not cursor.description:
        return []
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _run_sp_multi(sql, params, result_count):
    """Execute a multi-result-set stored procedure over ONE connection.

    Used instead of N separate `_run_sp` calls when several detail panels
    are needed together, to cut round trips per store from N to 1.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        results = [_rows_from_cursor(cursor)]
        for _ in range(result_count - 1):
            cursor.nextset()
            results.append(_rows_from_cursor(cursor))
        return results
    finally:
        cursor.close()
        conn.close()


# ----- Search (Tab 1: Product, Tab 2: Batch / MRP) ------------------------

def search_products(tenant_id, search_text, only_stock):
    return _run_sp(
        "EXEC stock.usp_ProductSearch @TenantId=?, @SearchText=?, @OnlyStock=?",
        (tenant_id, search_text, only_stock),
    )


def search_batches(tenant_id, batch_no, mrp, product_name):
    return _run_sp(
        "EXEC stock.usp_BatchSearch "
        "@TenantId=?, @BatchNo=?, @MRP=?, @ProductName=?",
        (tenant_id, batch_no, mrp, product_name),
    )


# ----- Detail panels (scoped by tenant + store + product) -----------------

def get_product_details(tenant_id, store_id, product_code):
    rows = _run_sp(
        "EXEC stock.usp_ProductDetails "
        "@TenantId=?, @StoreId=?, @ProductCode=?",
        (tenant_id, store_id, product_code),
    )
    return rows[0] if rows else None


def get_batch_details(tenant_id, store_id, product_code):
    return _run_sp(
        "EXEC stock.usp_BatchDetails "
        "@TenantId=?, @StoreId=?, @ProductCode=?",
        (tenant_id, store_id, product_code),
    )


def get_product_core(tenant_id, store_id, product_code, months=3):
    """batches + purchases + sales + movement in one round trip (perf)."""
    batches, purchases, sales, movement = _run_sp_multi(
        "EXEC stock.usp_ProductCore "
        "@TenantId=?, @StoreId=?, @ProductCode=?, @Months=?",
        (tenant_id, store_id, product_code, months),
        4,
    )
    return {
        "batches": batches,
        "purchases": purchases,
        "sales": sales,
        "movement": movement,
    }


def get_purchase_history(tenant_id, store_id, product_code):
    return _run_sp(
        "EXEC stock.usp_PurchaseHistory "
        "@TenantId=?, @StoreId=?, @ProductCode=?",
        (tenant_id, store_id, product_code),
    )


def get_sales_history(tenant_id, store_id, product_code):
    return _run_sp(
        "EXEC stock.usp_SalesHistory "
        "@TenantId=?, @StoreId=?, @ProductCode=?",
        (tenant_id, store_id, product_code),
    )


def get_bill_items(tenant_id, store_id, bill_no, bill_date):
    return _run_sp(
        "EXEC stock.usp_BillItems "
        "@TenantId=?, @StoreId=?, @BillNo=?, @BillDate=?",
        (tenant_id, store_id, bill_no, bill_date),
    )


def get_monthly_movement(tenant_id, store_id, product_code, months):
    return _run_sp(
        "EXEC stock.usp_MonthlyMovement "
        "@TenantId=?, @StoreId=?, @ProductCode=?, @Months=?",
        (tenant_id, store_id, product_code, months),
    )


# ----- Bill Drawer (Purchase Manager detail panel) ------------------------

def get_purchase_bill(tenant_id, store_id, grn_no, grn_date):
    return _run_sp(
        "EXEC stock.usp_PurchaseBill "
        "@TenantId=?, @StoreId=?, @GrnNo=?, @GrnDate=?",
        (tenant_id, store_id, grn_no, grn_date),
    )


def get_sales_bill(tenant_id, store_id, bill_no, bill_date):
    return _fetch(
        """
        ;WITH bill_match AS (
            SELECT TOP (1)
                si.tenant_id,
                si.store_id,
                si.BNumber,
                si.BillNumber,
                CAST(si.BillDate AS DATE) AS BillDate,
                si.CustomerName,
                CAST(si.CustomerCode AS NVARCHAR(100)) AS CustomerCode,
                ISNULL(si.BillAmount, 0) AS BillAmount,
                ISNULL(NULLIF(RTRIM(sr.Salesmanname), ''), '-') AS SalesmanName
            FROM sync.SaleInformation si
            LEFT JOIN sync.SalesRep sr
                ON sr.tenant_id = si.tenant_id
               AND sr.store_id = si.store_id
               AND sr.Salesmancode = si.DeliverySalesRep
            WHERE si.tenant_id = ?
              AND si.store_id = ?
              AND si.BNumber = ?
              AND (? IS NULL OR CAST(si.BillDate AS DATE) = CAST(? AS DATE))
            ORDER BY si.BillDate DESC, si.BillNumber DESC
        )
        SELECT
            bm.BNumber AS bill_no,
            bm.BillDate AS bill_date,
            bm.CustomerName AS customer,
            bm.CustomerCode AS customer_code,
            bm.SalesmanName AS salesman,
            bm.BillAmount AS bill_value,
            CAST(psi.ProductCode AS NVARCHAR(100)) AS product_code,
            ISNULL(p.ProductName, CAST(psi.ProductCode AS NVARCHAR(100))) AS product_name,
            ISNULL(psi.Batchdescription, '') AS batch,
            ISNULL(psi.Quantity, 0) AS qty,
            ISNULL(psi.MRP, 0) AS mrp,
            ISNULL(psi.DiscountPercentage, 0) AS discount,
            ISNULL(psi.Taxamount, 0) AS tax,
            CAST(ISNULL(psi.DontConsiderInOrder, 0) AS BIT) AS dont_consider_in_order
        FROM bill_match bm
        INNER JOIN sync.ProductSaleInformation psi
            ON psi.tenant_id = bm.tenant_id
           AND psi.store_id = bm.store_id
           AND psi.BillNumber = bm.BillNumber
           AND psi.SeriesName = LEFT(bm.BNumber, 1)
           AND CAST(psi.TransactionDate AS DATE) = bm.BillDate
        LEFT JOIN sync.Products p
            ON p.tenant_id = psi.tenant_id
           AND p.store_id = psi.store_id
           AND p.ProductCode = psi.ProductCode
        WHERE ISNULL(psi.TransactionValidity, 0) = 0
        ORDER BY ISNULL(p.ProductName, CAST(psi.ProductCode AS NVARCHAR(100))), ISNULL(psi.Batchdescription, '')
        """,
        (tenant_id, store_id, bill_no, bill_date, bill_date),
    )


def set_sales_bill_line_ignore(
    tenant_id,
    store_id,
    bill_no,
    bill_date,
    product_code,
    batch,
    dont_consider_in_order,
):
    return _execute(
        """
        UPDATE psi
        SET psi.DontConsiderInOrder = ?
        FROM sync.ProductSaleInformation psi
        WHERE psi.tenant_id = ?
          AND psi.store_id = ?
          AND psi.BNumber = ?
          AND psi.SeriesName = LEFT(?, 1)
          AND CAST(psi.TransactionDate AS DATE) = CAST(? AS DATE)
          AND CAST(psi.ProductCode AS NVARCHAR(100)) = CAST(? AS NVARCHAR(100))
          AND ISNULL(psi.TransactionValidity, 0) = 0
          AND (
                NULLIF(LTRIM(RTRIM(?)), '') IS NULL
                OR ISNULL(psi.Batchdescription, '') = ?
              )
        """,
        (
            1 if dont_consider_in_order else 0,
            tenant_id,
            store_id,
            bill_no,
            bill_no,
            bill_date,
            product_code,
            batch,
            batch,
        ),
    )


def get_product_availability(tenant_id, store_id, product_code):
    return _run_sp(
        "EXEC stock.usp_ProductAvailability "
        "@TenantId=?, @StoreId=?, @ProductCode=?",
        (tenant_id, store_id, product_code),
    )


def get_customer_history(tenant_id, store_id, customer_code):
    return _run_sp(
        "EXEC stock.usp_CustomerHistory "
        "@TenantId=?, @StoreId=?, @CustomerCode=?",
        (tenant_id, store_id, customer_code),
    )


def get_repeat_purchase(tenant_id, store_id, product_code):
    return _run_sp(
        "EXEC stock.usp_RepeatPurchase "
        "@TenantId=?, @StoreId=?, @ProductCode=?",
        (tenant_id, store_id, product_code),
    )
