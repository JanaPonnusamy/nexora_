/* ============================================================================
   NEXORA PLATFORM — Purchase Manager detail / Bill Drawer stored procedures
   Target database : NEXORA_PLATFORM        (run everything here, never OrderNMC)
   Source data     : sync.[<Table>]         (synced business tables; each row
                                              carries store_id + tenant_id)

   These extend the Stock Availability procedures with the Bill Drawer + drawer
   tabs used by the Purchase Manager detail panel. All read-only, all adapted
   from the proven legacy OrderNMC bodies.

   NOTE (schema now richer than the original stock SPs assumed):
     * sync.PurchaseTrans DOES carry SupplierCode now  → usp_PurchaseHistory /
       usp_PurchaseBill resolve the supplier NAME via sync.Suppliers.
     * sync.SalesRep IS synced now → usp_SalesHistory / usp_SalesBill resolve the
       delivery Sales Rep via sync.SaleInformation.DeliverySalesRep.
   ============================================================================ */

IF SCHEMA_ID(N'stock') IS NULL
    EXEC(N'CREATE SCHEMA stock');
GO

/* ---------------------------------------------------------------------------
   1) stock.usp_PurchaseHistory  (REPLACE — now resolves the Supplier name)
   OUTPUT: grn_no, date, qty, free, dis, cost, ptr, mrp, supplier
   --------------------------------------------------------------------------- */
IF OBJECT_ID(N'stock.usp_PurchaseHistory', N'P') IS NOT NULL DROP PROCEDURE stock.usp_PurchaseHistory;
GO
CREATE PROCEDURE stock.usp_PurchaseHistory
    @TenantId UNIQUEIDENTIFIER, @StoreId UNIQUEIDENTIFIER, @ProductCode INT
AS
BEGIN
    SET NOCOUNT ON;
    -- Internal 'TI' (Transfer-In) rows resolve to the tenant warehouse
    -- (dbo.stores.is_warehouse = 1), NOT the colliding SupplierCode which shares
    -- the local supplier-code namespace. Genuine purchases are unchanged.
    SELECT TOP (15)
        CAST(pt.Grnnumber AS NVARCHAR(50))  AS grn_no,
        CAST(pt.grndate AS DATE)            AS [date],
        ISNULL(pt.stockreceived, 0)         AS qty,
        ISNULL(pt.FreeQty, 0)               AS free,
        ISNULL(pt.ProductDiscPercent, 0)    AS dis,
        ISNULL(pt.itemcost, 0)              AS cost,
        ISNULL(pt.purchaseprice, 0)         AS ptr,
        ISNULL(pt.mrp, 0)                   AS mrp,
        RTRIM(pt.InvoiceSeries)             AS invoice_series,
        CASE WHEN RTRIM(pt.InvoiceSeries) = 'TI' THEN 'transfer' ELSE 'supplier' END AS party_type,
        CASE WHEN RTRIM(pt.InvoiceSeries) = 'TI'
             THEN ISNULL(NULLIF(RTRIM(wh.store_code), ''), 'Transfer')
             ELSE ISNULL(NULLIF(RTRIM(s.suppliername), ''), CAST(pt.SupplierCode AS NVARCHAR(100)))
        END                                 AS supplier,
        CASE WHEN RTRIM(pt.InvoiceSeries) = 'TI' THEN wh.store_name END AS source_store_name
    FROM sync.PurchaseTrans pt
    LEFT JOIN sync.Suppliers s
           ON s.tenant_id = pt.tenant_id AND s.store_id = pt.store_id
          AND CAST(s.suppliercode AS VARCHAR(100)) = CAST(pt.SupplierCode AS VARCHAR(100))
    OUTER APPLY (
        SELECT TOP (1) w.store_code, w.store_name
        FROM dbo.stores w
        WHERE w.tenant_id = pt.tenant_id AND w.is_warehouse = 1
        ORDER BY w.store_code
    ) wh
    WHERE pt.tenant_id = @TenantId AND pt.store_id = @StoreId AND pt.ProductCode = @ProductCode
    ORDER BY pt.grndate DESC;
END
GO

/* ---------------------------------------------------------------------------
   2) stock.usp_SalesHistory  (REPLACE — now resolves the delivery Sales Rep)
   OUTPUT: date, bill_no, customer, qty, mrp, discount, salesman
   --------------------------------------------------------------------------- */
IF OBJECT_ID(N'stock.usp_SalesHistory', N'P') IS NOT NULL DROP PROCEDURE stock.usp_SalesHistory;
GO
CREATE PROCEDURE stock.usp_SalesHistory
    @TenantId UNIQUEIDENTIFIER, @StoreId UNIQUEIDENTIFIER, @ProductCode INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (50)
        CAST(psi.TransactionDate AS DATE)   AS [date],
        psi.Bnumber                         AS bill_no,
        si.CustomerName                     AS customer,
        ISNULL(psi.Quantity, 0)             AS qty,
        ISNULL(psi.MRP, 0)                  AS mrp,
        ISNULL(psi.DiscountPercentage, 0)   AS discount,
        ISNULL(NULLIF(RTRIM(sr.Salesmanname), ''), '-') AS salesman
    FROM sync.ProductSaleInformation psi
    LEFT JOIN sync.SaleInformation si
           ON si.tenant_id = psi.tenant_id AND si.store_id = psi.store_id
          AND si.BNumber = psi.Bnumber
          AND CAST(si.BillDate AS DATE) = CAST(psi.TransactionDate AS DATE)
    LEFT JOIN sync.SalesRep sr
           ON sr.store_id = si.store_id
          AND sr.Salesmancode = si.DeliverySalesRep
    WHERE psi.tenant_id = @TenantId AND psi.store_id = @StoreId
      AND psi.ProductCode = @ProductCode
      AND ISNULL(psi.TransactionValidity, 0) = 0
    ORDER BY psi.TransactionDate DESC;
END
GO

/* ---------------------------------------------------------------------------
   3) stock.usp_PurchaseBill  (NEW — Purchase Bill Drawer)
   All lines of one GRN. Header fields are denormalised onto every row (the
   caller reads them from the first row + sums the purchase value).
   OUTPUT: grn_no, invoice_series, bill_date, supplier, supplier_code,
           product_name, batch, expiry, qty, free, ptr, mrp, tax, discount, margin
   --------------------------------------------------------------------------- */
IF OBJECT_ID(N'stock.usp_PurchaseBill', N'P') IS NOT NULL DROP PROCEDURE stock.usp_PurchaseBill;
GO
CREATE PROCEDURE stock.usp_PurchaseBill
    @TenantId UNIQUEIDENTIFIER, @StoreId UNIQUEIDENTIFIER,
    @GrnNo INT, @GrnDate DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    -- 'TI' (Transfer-In) rows are internal transfers: resolve the party to the
    -- tenant warehouse (is_warehouse = 1), not the colliding SupplierCode.
    SELECT
        CAST(pt.Grnnumber AS NVARCHAR(50))  AS grn_no,
        RTRIM(pt.InvoiceSeries)             AS invoice_series,
        CAST(pt.grndate AS DATE)            AS bill_date,
        CASE WHEN RTRIM(pt.InvoiceSeries) = 'TI' THEN 'transfer' ELSE 'supplier' END AS party_type,
        CASE WHEN RTRIM(pt.InvoiceSeries) = 'TI'
             THEN ISNULL(NULLIF(RTRIM(wh.store_code), ''), 'Transfer')
             ELSE ISNULL(NULLIF(RTRIM(s.suppliername), ''), CAST(pt.SupplierCode AS NVARCHAR(100)))
        END                                 AS supplier,
        CASE WHEN RTRIM(pt.InvoiceSeries) = 'TI' THEN wh.store_name END AS source_store_name,
        CAST(pt.SupplierCode AS NVARCHAR(100)) AS supplier_code,
        ISNULL(p.ProductName, CAST(pt.ProductCode AS NVARCHAR(50))) AS product_name,
        CAST(pt.BatchCode AS NVARCHAR(50))  AS batch,
        CAST(b.ExpiryDate AS DATE)          AS expiry,
        ISNULL(pt.stockreceived, 0)         AS qty,
        ISNULL(pt.FreeQty, 0)               AS free,
        ISNULL(pt.purchaseprice, 0)         AS ptr,
        ISNULL(pt.mrp, 0)                   AS mrp,
        ISNULL(pt.TaxAmount, 0)             AS tax,
        ISNULL(pt.DiscountAmount, 0)        AS discount,
        ISNULL(pt.Margin, 0)               AS margin
    FROM sync.PurchaseTrans pt
    LEFT JOIN sync.Products p
           ON p.tenant_id = pt.tenant_id AND p.store_id = pt.store_id AND p.ProductCode = pt.ProductCode
    LEFT JOIN sync.Suppliers s
           ON s.tenant_id = pt.tenant_id AND s.store_id = pt.store_id
          AND CAST(s.suppliercode AS VARCHAR(100)) = CAST(pt.SupplierCode AS VARCHAR(100))
    LEFT JOIN sync.Batches b
           ON b.tenant_id = pt.tenant_id AND b.store_id = pt.store_id
          AND b.BatchCode = pt.BatchCode AND b.ProductCode = pt.ProductCode
    OUTER APPLY (
        SELECT TOP (1) w.store_code, w.store_name
        FROM dbo.stores w
        WHERE w.tenant_id = pt.tenant_id AND w.is_warehouse = 1
        ORDER BY w.store_code
    ) wh
    WHERE pt.tenant_id = @TenantId AND pt.store_id = @StoreId AND pt.Grnnumber = @GrnNo
      AND (@GrnDate IS NULL OR CAST(pt.grndate AS DATE) = @GrnDate)
    ORDER BY p.ProductName;
END
GO

/* ---------------------------------------------------------------------------
   4) stock.usp_SalesBill  (NEW — Sales Bill Drawer)
   All lines of one sale bill (Bnumber). Header denormalised onto every row.
   OUTPUT: bill_no, bill_date, customer, customer_code, salesman, bill_value,
           product_name, batch, qty, mrp, discount, tax
   --------------------------------------------------------------------------- */
IF OBJECT_ID(N'stock.usp_SalesBill', N'P') IS NOT NULL DROP PROCEDURE stock.usp_SalesBill;
GO
CREATE PROCEDURE stock.usp_SalesBill
    @TenantId UNIQUEIDENTIFIER, @StoreId UNIQUEIDENTIFIER,
    @BillNo NVARCHAR(50), @BillDate DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    ;WITH bm AS (
        SELECT TOP (1)
            si.store_id, si.tenant_id, si.BNumber, si.BillNumber,
            CAST(si.BillDate AS DATE) AS BillDate,
            si.CustomerName, CAST(si.CustomerCode AS NVARCHAR(100)) AS CustomerCode,
            ISNULL(si.BillAmount, 0) AS BillAmount,
            ISNULL(NULLIF(RTRIM(sr.Salesmanname), ''), '-') AS SalesmanName
        FROM sync.SaleInformation si
        LEFT JOIN sync.SalesRep sr
               ON sr.store_id = si.store_id
              AND sr.Salesmancode = si.DeliverySalesRep
        WHERE si.tenant_id = @TenantId AND si.store_id = @StoreId AND si.BNumber = @BillNo
          AND (@BillDate IS NULL OR CAST(si.BillDate AS DATE) = @BillDate)
        ORDER BY si.BillDate DESC
    )
    SELECT
        bm.BNumber           AS bill_no,
        bm.BillDate          AS bill_date,
        bm.CustomerName      AS customer,
        bm.CustomerCode      AS customer_code,
        bm.SalesmanName      AS salesman,
        bm.BillAmount        AS bill_value,
        ISNULL(p.ProductName, CAST(psi.ProductCode AS NVARCHAR(50))) AS product_name,
        ISNULL(psi.Batchdescription, '') AS batch,
        ISNULL(psi.Quantity, 0)          AS qty,
        ISNULL(psi.MRP, 0)               AS mrp,
        ISNULL(psi.DiscountPercentage, 0) AS discount,
        ISNULL(psi.Taxamount, 0)         AS tax
    FROM bm
    INNER JOIN sync.ProductSaleInformation psi
            ON psi.tenant_id = bm.tenant_id AND psi.store_id = bm.store_id
           AND psi.BillNumber = bm.BillNumber
           AND psi.SeriesName = LEFT(bm.BNumber, 1)
           AND CAST(psi.TransactionDate AS DATE) = bm.BillDate
    INNER JOIN sync.Products p
            ON p.tenant_id = psi.tenant_id AND p.store_id = psi.store_id AND p.ProductCode = psi.ProductCode
    WHERE ISNULL(psi.TransactionValidity, 0) = 0
    ORDER BY p.ProductName;
END
GO

/* ---------------------------------------------------------------------------
   5) stock.usp_ProductAvailability  (NEW — drawer Availability tab)
   Per-store stock for a product across the tenant (current store flagged) plus
   the quantity still on order (assigned − received) from open procurement rows.
   OUTPUT: store_id, store_code, store_name, stock, is_current, pending_qty
   --------------------------------------------------------------------------- */
IF OBJECT_ID(N'stock.usp_ProductAvailability', N'P') IS NOT NULL DROP PROCEDURE stock.usp_ProductAvailability;
GO
CREATE PROCEDURE stock.usp_ProductAvailability
    @TenantId UNIQUEIDENTIFIER, @StoreId UNIQUEIDENTIFIER, @ProductCode INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        CAST(st.store_id AS NVARCHAR(50)) AS store_id,
        st.store_code, st.store_name,
        ISNULL(p.TotalStock, 0)           AS stock,
        CASE WHEN st.store_id = @StoreId THEN 1 ELSE 0 END AS is_current,
        ISNULL(pend.pending_qty, 0)       AS pending_qty
    FROM dbo.stores st
    LEFT JOIN sync.Products p
           ON p.tenant_id = st.tenant_id AND p.store_id = st.store_id AND p.ProductCode = @ProductCode
    LEFT JOIN (
        SELECT oi.store_id,
               SUM(ISNULL(oi.assigned_qty, 0) - ISNULL(oi.received_qty, 0)) AS pending_qty
        FROM procurement.procurement_order_items oi
        WHERE oi.tenant_id = @TenantId AND oi.is_deleted = 0
          AND CAST(oi.product_code AS VARCHAR(100)) = CAST(@ProductCode AS VARCHAR(100))
          AND ISNULL(oi.assigned_qty, 0) > ISNULL(oi.received_qty, 0)
        GROUP BY oi.store_id
    ) pend ON pend.store_id = st.store_id
    WHERE st.tenant_id = @TenantId AND st.is_active = 1
    ORDER BY is_current DESC, stock DESC;
END
GO

/* ---------------------------------------------------------------------------
   6) stock.usp_CustomerHistory  (NEW — drawer Customer History tab)
   The customer's last 10 bills with their total quantity, so the panel can show
   frequency (count), last purchase (first row) and average quantity.
   OUTPUT: bill_no, date, bill_value, total_qty
   --------------------------------------------------------------------------- */
IF OBJECT_ID(N'stock.usp_CustomerHistory', N'P') IS NOT NULL DROP PROCEDURE stock.usp_CustomerHistory;
GO
CREATE PROCEDURE stock.usp_CustomerHistory
    @TenantId UNIQUEIDENTIFIER, @StoreId UNIQUEIDENTIFIER, @CustomerCode NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    IF @CustomerCode IS NULL OR LTRIM(RTRIM(@CustomerCode)) IN ('', '0') RETURN;
    SELECT TOP (10)
        si.BNumber                AS bill_no,
        CAST(si.BillDate AS DATE) AS [date],
        ISNULL(si.BillAmount, 0)  AS bill_value,
        ISNULL(li.total_qty, 0)   AS total_qty
    FROM sync.SaleInformation si
    OUTER APPLY (
        SELECT SUM(ISNULL(psi.Quantity, 0)) AS total_qty
        FROM sync.ProductSaleInformation psi
        WHERE psi.tenant_id = si.tenant_id AND psi.store_id = si.store_id
          AND psi.BillNumber = si.BillNumber
          AND psi.SeriesName = LEFT(si.BNumber, 1)
          AND CAST(psi.TransactionDate AS DATE) = CAST(si.BillDate AS DATE)
          AND ISNULL(psi.TransactionValidity, 0) = 0
    ) li
    WHERE si.tenant_id = @TenantId AND si.store_id = @StoreId
      AND CAST(si.CustomerCode AS NVARCHAR(100)) = @CustomerCode
    ORDER BY si.BillDate DESC;
END
GO

/* ---------------------------------------------------------------------------
   7) stock.usp_RepeatPurchase  (NEW — drawer Repeat Purchase tab)
   Products most frequently bought in the SAME bill as this product ("usually
   bought together"), over the product's most recent 500 bills (bounded).
   OUTPUT: product_name, times_together
   --------------------------------------------------------------------------- */
IF OBJECT_ID(N'stock.usp_RepeatPurchase', N'P') IS NOT NULL DROP PROCEDURE stock.usp_RepeatPurchase;
GO
CREATE PROCEDURE stock.usp_RepeatPurchase
    @TenantId UNIQUEIDENTIFIER, @StoreId UNIQUEIDENTIFIER, @ProductCode INT
AS
BEGIN
    SET NOCOUNT ON;
    ;WITH bills AS (
        SELECT TOP (500) psi.BillNumber, psi.SeriesName,
               CAST(psi.TransactionDate AS DATE) AS d
        FROM sync.ProductSaleInformation psi
        WHERE psi.tenant_id = @TenantId AND psi.store_id = @StoreId
          AND psi.ProductCode = @ProductCode
          AND ISNULL(psi.TransactionValidity, 0) = 0
        GROUP BY psi.BillNumber, psi.SeriesName, CAST(psi.TransactionDate AS DATE)
        ORDER BY MAX(psi.TransactionDate) DESC
    )
    SELECT TOP (10)
        ISNULL(p.ProductName, CAST(psi.ProductCode AS NVARCHAR(50))) AS product_name,
        COUNT(DISTINCT CAST(psi.BillNumber AS NVARCHAR(20)) + psi.SeriesName + CONVERT(NVARCHAR(10), psi.TransactionDate, 112)) AS times_together
    FROM bills b
    INNER JOIN sync.ProductSaleInformation psi
            ON psi.BillNumber = b.BillNumber AND psi.SeriesName = b.SeriesName
           AND CAST(psi.TransactionDate AS DATE) = b.d
    INNER JOIN sync.Products p
            ON p.tenant_id = psi.tenant_id AND p.store_id = psi.store_id AND p.ProductCode = psi.ProductCode
    WHERE psi.tenant_id = @TenantId AND psi.store_id = @StoreId
      AND psi.ProductCode <> @ProductCode
      AND ISNULL(psi.TransactionValidity, 0) = 0
    GROUP BY p.ProductName, psi.ProductCode
    ORDER BY times_together DESC;
END
GO
