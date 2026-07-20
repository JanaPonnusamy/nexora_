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
    return _run_sp(
        "EXEC stock.usp_SalesBill "
        "@TenantId=?, @StoreId=?, @BillNo=?, @BillDate=?",
        (tenant_id, store_id, bill_no, bill_date),
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
