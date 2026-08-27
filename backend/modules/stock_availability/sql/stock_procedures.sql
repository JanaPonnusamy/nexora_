/* ============================================================================
   NEXORA PLATFORM — Stock Availability stored procedures
   Target database : NEXORA_PLATFORM        (run everything here, never OrderNMC)
   Source data     : sync.[<Table>]         (synced business tables; each row
                                              carries store_id + tenant_id)
   Store master    : dbo.stores             (store_id GUID, tenant_id,
                                              store_code, store_name)

   These are the NEXORA equivalents of the proven legacy OrderNMC procedures,
   adapted (NOT redesigned) from their original bodies:
       sp_ProductStoreGrid              -> stock.usp_ProductSearch
       sp_BatchDetails (search angle)   -> stock.usp_BatchSearch
       (Products header + ProductTrans) -> stock.usp_ProductDetails
       sp_BatchDetails                  -> stock.usp_BatchDetails
       sp_nmstock_get_purchases         -> stock.usp_PurchaseHistory
       sp_nmstock_get_sales             -> stock.usp_SalesHistory
       sp_nmstock_get_bill_items        -> stock.usp_BillItems
       usp_GetProductTransTimelineChart -> stock.usp_MonthlyMovement

   ADAPTATIONS forced by the synced schema (legacy logic otherwise preserved):
     * Legacy filtered on a StoreName column = the store CODE. The synced tables
       do not carry it, so every filter is store_id + tenant_id (GUIDs) instead,
       joined to dbo.stores for code/name.
     * sp_nmstock_get_purchases dropped `Sync = 0` (column not synced); supplier
       name is joined from sync.Suppliers via PurchaseTrans.SupplierCode.
     * sp_nmstock_get_bill_items dropped the SalesRep join (table not synced).
     * sp_nmstock_get_sales additionally exposes MRP (column exists; the UI grid
       shows it) — same rows, one extra column.
   Read-only: no writes, no temp business tables.
   ============================================================================ */

IF SCHEMA_ID(N'stock') IS NULL
    EXEC(N'CREATE SCHEMA stock');
GO

/* ===========================================================================
   1) stock.usp_ProductSearch   (Tab 1 — Product Search)
   Partial, case-insensitive product search across every branch of a tenant.
   Caps @PerStore rows per branch (legacy showed the top N per store).
   OUTPUT: store_id, store_code, store_name,
           product_code, product_name, sale_unit, stock, mrp
   =========================================================================== */
IF OBJECT_ID(N'stock.usp_ProductSearch', N'P') IS NOT NULL DROP PROCEDURE stock.usp_ProductSearch;
GO
CREATE PROCEDURE stock.usp_ProductSearch
    @TenantId    UNIQUEIDENTIFIER,
    @SearchText  NVARCHAR(100) = NULL,
    @OnlyStock   BIT           = 0,
    @PerStore    INT           = 20
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Search NVARCHAR(100) = NULLIF(LTRIM(RTRIM(@SearchText)), '');

    ;WITH filtered AS
    (
        SELECT
            s.store_id, s.store_code, s.store_name, s.store_order,
            p.ProductCode, p.ProductName, p.UnitDescription,
            p.TotalStock AS RawTotalStock,
            ISNULL(p.MRP, 0) AS MRP
        FROM sync.Products p
        INNER JOIN dbo.stores s
                ON s.store_id  = p.store_id
               AND s.tenant_id = p.tenant_id
        WHERE p.tenant_id = @TenantId
          AND ISNULL(p.isActive, 1) = 1
          AND (
                @Search IS NULL
                OR p.ProductName LIKE @Search + '%'
                OR CAST(p.ProductCode AS NVARCHAR(50)) LIKE @Search + '%'
              )
    ),
    stocked AS
    (
        -- Product Grid stock MUST equal SUM(batch stock WHERE Stock > 0) for
        -- any product that is batch-tracked (has rows in sync.Batches) -
        -- ProductTrans.StockInHand/Products.TotalStock are periodic
        -- (monthly) snapshots that drift from the live batch ledger and
        -- caused Product Grid vs Batch Grid to disagree (e.g. "13" vs "20+"
        -- for the same product). Only products with NO batch rows at all
        -- (not batch-tracked) fall back to the old snapshot chain.
        SELECT
            f.store_id, f.store_code, f.store_name, f.store_order,
            f.ProductCode, f.ProductName, f.UnitDescription, f.MRP,
            COALESCE(
                CASE WHEN bs.BatchRowCount > 0 THEN ISNULL(bs.BatchStock, 0) END,
                pt.StockInHand,
                f.RawTotalStock,
                0
            ) AS TotalStock
        FROM filtered f
        OUTER APPLY (
            SELECT
                SUM(CASE WHEN b.Stock > 0 THEN b.Stock ELSE 0 END) AS BatchStock,
                COUNT(*) AS BatchRowCount
            FROM sync.Batches b
            WHERE b.store_id    = f.store_id
              AND b.tenant_id   = @TenantId
              AND b.ProductCode = f.ProductCode
        ) bs
        OUTER APPLY (
            SELECT TOP (1) pt.StockInHand
            FROM sync.ProductTrans pt
            WHERE pt.store_id = f.store_id
              AND pt.ProductCode = f.ProductCode
            ORDER BY pt.MonthOfStatistics DESC
        ) pt
    ),
    ranked AS
    (
        SELECT
            store_id, store_code, store_name, store_order,
            ProductCode, ProductName, UnitDescription, TotalStock, MRP,
            ROW_NUMBER() OVER
            (
                PARTITION BY store_id
                ORDER BY
                    CASE WHEN @Search IS NULL THEN ProductName END,
                    CASE WHEN @Search IS NOT NULL THEN TotalStock END DESC,
                    ProductName
            ) AS rn
        FROM stocked
        WHERE @OnlyStock = 0 OR TotalStock > 0
    )
    SELECT
        store_id,
        store_code,
        store_name,
        CAST(ProductCode AS NVARCHAR(50)) AS product_code,
        ProductName                       AS product_name,
        UnitDescription                   AS sale_unit,
        TotalStock                        AS stock,
        MRP                               AS mrp
    FROM ranked
    WHERE rn <= @PerStore
    ORDER BY store_order, store_code, product_name;
END
GO

/* ===========================================================================
   2) stock.usp_BatchSearch   (Tab 2 — Batch / MRP Search)
   Search by batch number, MRP and/or product name across branches, off the
   batch table. OUTPUT = usp_ProductSearch columns + batch_no.
   =========================================================================== */
IF OBJECT_ID(N'stock.usp_BatchSearch', N'P') IS NOT NULL DROP PROCEDURE stock.usp_BatchSearch;
GO
CREATE PROCEDURE stock.usp_BatchSearch
    @TenantId     UNIQUEIDENTIFIER,
    @BatchNo      NVARCHAR(100)  = NULL,
    @MRP          DECIMAL(18, 2) = NULL,
    @ProductName  NVARCHAR(200)  = NULL,
    @PerStore     INT            = 20
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @B  NVARCHAR(100) = NULLIF(LTRIM(RTRIM(@BatchNo)), '');
    DECLARE @PN NVARCHAR(200) = NULLIF(LTRIM(RTRIM(@ProductName)), '');

    ;WITH ranked AS
    (
        SELECT
            s.store_id, s.store_code, s.store_name, s.store_order,
            b.ProductCode, p.ProductName, p.UnitDescription,
            ISNULL(b.Stock, 0) AS Stock,
            ISNULL(b.MRP, 0)   AS MRP,
            b.BatchCode,
            ROW_NUMBER() OVER
            (
                PARTITION BY s.store_id
                ORDER BY ISNULL(b.Stock, 0) DESC, p.ProductName
            ) AS rn
        FROM sync.Batches b
        INNER JOIN dbo.stores s
                ON s.store_id  = b.store_id
               AND s.tenant_id = b.tenant_id
        LEFT JOIN sync.Products p
                ON p.store_id    = b.store_id
               AND p.tenant_id   = b.tenant_id
               AND p.ProductCode = b.ProductCode
        WHERE b.tenant_id = @TenantId
          AND (@B   IS NULL OR CAST(b.BatchCode AS NVARCHAR(50)) LIKE @B + '%')
          AND (@MRP IS NULL OR b.MRP = @MRP)
          AND (@PN  IS NULL OR p.ProductName LIKE '%' + @PN + '%')
    )
    SELECT
        store_id,
        store_code,
        store_name,
        CAST(ProductCode AS NVARCHAR(50)) AS product_code,
        ProductName                       AS product_name,
        UnitDescription                   AS sale_unit,
        Stock                             AS stock,
        MRP                               AS mrp,
        CAST(BatchCode AS NVARCHAR(50))   AS batch_no
    FROM ranked
    WHERE rn <= @PerStore
    ORDER BY store_order, store_code, product_name;
END
GO

/* ===========================================================================
   3) stock.usp_ProductDetails   (header panel for the active product)
   OUTPUT (single row): product_code, product_name, sale_unit, mrp, packing,
                        sublocation, total_stock, last_sale, last_purchase
   Attributes are taken from the product's first batch (in-stock first, then
   earliest expiry); total_stock is the summed batch stock; last_sale /
   last_purchase come from ProductTrans.
   =========================================================================== */
IF OBJECT_ID(N'stock.usp_ProductDetails', N'P') IS NOT NULL DROP PROCEDURE stock.usp_ProductDetails;
GO
CREATE PROCEDURE stock.usp_ProductDetails
    @TenantId     UNIQUEIDENTIFIER,
    @StoreId      UNIQUEIDENTIFIER,
    @ProductCode  INT
AS
BEGIN
    SET NOCOUNT ON;

    ;WITH fb AS
    (
        SELECT TOP (1) b.MRP, b.SaleUnit, b.SubLocation
        FROM sync.Batches b
        WHERE b.tenant_id = @TenantId AND b.store_id = @StoreId
          AND b.ProductCode = @ProductCode
        ORDER BY CASE WHEN ISNULL(b.Stock, 0) > 0 THEN 0 ELSE 1 END, b.ExpiryDate
    )
    SELECT TOP (1)
        CAST(p.ProductCode AS NVARCHAR(50)) AS product_code,
        p.ProductName                       AS product_name,
        p.UnitDescription                   AS sale_unit,
        COALESCE(fb.MRP, p.MRP, 0)          AS mrp,
        fb.SaleUnit                         AS packing,
        COALESCE(NULLIF(LTRIM(RTRIM(fb.SubLocation)), ''),
                 NULLIF(LTRIM(RTRIM(p.SubLocation)), '')) AS sublocation,
        -- total_stock = SUM(batch stock WHERE Stock > 0) whenever the product
        -- is batch-tracked (has any row in sync.Batches, even if all are
        -- currently zero/negative) - a handful of batches carry negative
        -- Stock (POS correction rows) which must not net against real
        -- positive stock, and none of them may fall back to the stale
        -- Products.TotalStock snapshot just because the positive sum is 0.
        -- Only products with NO batch rows at all use that snapshot.
        (CASE WHEN EXISTS (
            SELECT 1 FROM sync.Batches b2
            WHERE b2.tenant_id = @TenantId AND b2.store_id = @StoreId
              AND b2.ProductCode = @ProductCode
        ) THEN (
            SELECT ISNULL(SUM(b3.Stock), 0)
            FROM sync.Batches b3
            WHERE b3.tenant_id = @TenantId AND b3.store_id = @StoreId
              AND b3.ProductCode = @ProductCode
              AND b3.Stock > 0
        ) ELSE ISNULL(p.TotalStock, 0) END)  AS total_stock,
        (
            SELECT MAX(t.LastBillDate)
            FROM sync.ProductTrans t
            WHERE t.tenant_id = @TenantId AND t.store_id = @StoreId
              AND t.ProductCode = p.ProductCode
        )                                   AS last_sale,
        (
            SELECT MAX(t.LastGrnDate)
            FROM sync.ProductTrans t
            WHERE t.tenant_id = @TenantId AND t.store_id = @StoreId
              AND t.ProductCode = p.ProductCode
        )                                   AS last_purchase
    FROM sync.Products p
    LEFT JOIN fb ON 1 = 1
    WHERE p.tenant_id = @TenantId
      AND p.store_id  = @StoreId
      AND p.ProductCode = @ProductCode;
END
GO

/* ===========================================================================
   4) stock.usp_BatchDetails   (Batch Details panel)
   Returns EVERY batch for the product/store (zero-stock included - the old
   5-row cap with zero-stock backfill hid real batches and made "Display all
   batches, don't hide zero-stock ones" impossible). Purchase Age / Sales Age
   are returned as raw day counts + source dates; status/priority/sort math
   (which needs "today", stock>0 filtering, and the near-expiry threshold) is
   business logic and lives in one place - the frontend - rather than being
   duplicated here and risking SQL/UI drift.
   OUTPUT: batch_no, stock, expiry_date, ptr, mrp, last_purchase_date,
   last_sale_date, purchase_age_days, sales_age_days
   =========================================================================== */
IF OBJECT_ID(N'stock.usp_BatchDetails', N'P') IS NOT NULL DROP PROCEDURE stock.usp_BatchDetails;
GO
CREATE PROCEDURE stock.usp_BatchDetails
    @TenantId     UNIQUEIDENTIFIER,
    @StoreId      UNIQUEIDENTIFIER,
    @ProductCode  INT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        CAST(b.BatchCode AS VARCHAR(50))         AS batch_no,
        ISNULL(b.Stock, 0)                       AS stock,
        CAST(b.ExpiryDate AS DATE)                AS expiry_date,
        ISNULL(b.PurchasePrice, 0)               AS ptr,
        ISNULL(b.MRP, 0)                         AS mrp,
        CAST(b.GrnDate AS DATE)                   AS last_purchase_date,
        CAST(b.LastSaleDate AS DATE)              AS last_sale_date,
        DATEDIFF(DAY, b.GrnDate, GETDATE())      AS purchase_age_days,
        DATEDIFF(DAY, b.LastSaleDate, GETDATE()) AS sales_age_days
    FROM sync.Batches b
    WHERE b.tenant_id = @TenantId
      AND b.store_id  = @StoreId
      AND b.ProductCode = @ProductCode
    ORDER BY
        CASE WHEN ISNULL(b.Stock, 0) > 0 THEN 0 ELSE 1 END,
        b.ExpiryDate;
END
GO

/* ===========================================================================
   4b) stock.usp_BatchDetail   (single-batch detail popup)
   Full detail for ONE batch of a product, shown when the user clicks a batch
   row. Everything comes straight off sync.Batches (which carries ItemCost +
   SupplierCode per batch); supplier name resolved via sync.Suppliers.
   OUTPUT: batch_no, batch_description, stock, expiry_date, cost, ptr, mrp,
           supplier, last_purchase_date, last_sale_date
   =========================================================================== */
IF OBJECT_ID(N'stock.usp_BatchDetail', N'P') IS NOT NULL DROP PROCEDURE stock.usp_BatchDetail;
GO
CREATE PROCEDURE stock.usp_BatchDetail
    @TenantId     UNIQUEIDENTIFIER,
    @StoreId      UNIQUEIDENTIFIER,
    @ProductCode  INT,
    @BatchCode    VARCHAR(50)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP (1)
        CAST(b.BatchCode AS VARCHAR(50))          AS batch_no,
        LTRIM(RTRIM(ISNULL(b.BatchDescription, ''))) AS batch_description,
        ISNULL(b.Stock, 0)                        AS stock,
        CAST(b.ExpiryDate AS DATE)                 AS expiry_date,
        ISNULL(b.ItemCost, 0)                     AS cost,
        ISNULL(b.PurchasePrice, 0)                AS ptr,
        ISNULL(b.MRP, 0)                          AS mrp,
        ISNULL(NULLIF(RTRIM(s.suppliername), ''), CAST(b.SupplierCode AS NVARCHAR(100))) AS supplier,
        CAST(b.GrnDate AS DATE)                    AS last_purchase_date,
        CAST(b.LastSaleDate AS DATE)               AS last_sale_date
    FROM sync.Batches b
    LEFT JOIN sync.Suppliers s
           ON s.tenant_id = b.tenant_id
          AND s.store_id  = b.store_id
          AND CAST(s.suppliercode AS VARCHAR(100)) = CAST(b.SupplierCode AS VARCHAR(100))
    WHERE b.tenant_id = @TenantId
      AND b.store_id  = @StoreId
      AND b.ProductCode = @ProductCode
      AND CAST(b.BatchCode AS VARCHAR(50)) = @BatchCode;
END
GO

/* ===========================================================================
   5) stock.usp_PurchaseHistory   (Recent Purchases panel)
   Faithful to sp_nmstock_get_purchases, plus supplier name via
   PurchaseTrans.SupplierCode -> sync.Suppliers (same join pattern as
   backend/modules/procurement/supplier_repository.py).
   OUTPUT: grn_no, date, qty, free, dis, ptr, mrp, supplier
   =========================================================================== */
IF OBJECT_ID(N'stock.usp_PurchaseHistory', N'P') IS NOT NULL DROP PROCEDURE stock.usp_PurchaseHistory;
GO
CREATE PROCEDURE stock.usp_PurchaseHistory
    @TenantId     UNIQUEIDENTIFIER,
    @StoreId      UNIQUEIDENTIFIER,
    @ProductCode  INT
AS
BEGIN
    SET NOCOUNT ON;

    -- Internal stock transfers (InvoiceSeries 'TI' = Transfer-In) are NOT
    -- external purchases: their SupplierCode is a transfer/source code that
    -- collides with the store-local supplier-code namespace (e.g. code 2 = a
    -- real supplier "PENTACARE"), so it must NOT be resolved via sync.Suppliers.
    -- For a transfer we surface the tenant's warehouse (dbo.stores.is_warehouse
    -- = 1) as the source party. Genuine purchases (series 'IV' etc.) are
    -- unchanged and keep resolving the real supplier name.
    SELECT TOP (15)
        CAST(pt.Grnnumber AS NVARCHAR(50)) AS grn_no,
        CAST(pt.grndate AS DATE)           AS [date],
        ISNULL(pt.stockreceived, 0)        AS qty,
        ISNULL(pt.FreeQty, 0)              AS free,
        ISNULL(pt.ProductDiscPercent, 0)   AS dis,
        ISNULL(pt.itemcost, 0)             AS cost,
        ISNULL(pt.purchaseprice, 0)        AS ptr,
        ISNULL(pt.mrp, 0)                  AS mrp,
        RTRIM(pt.InvoiceSeries)            AS invoice_series,
        CASE WHEN RTRIM(pt.InvoiceSeries) = 'TI' THEN 'transfer' ELSE 'supplier' END AS party_type,
        CASE WHEN RTRIM(pt.InvoiceSeries) = 'TI'
             THEN ISNULL(NULLIF(RTRIM(wh.store_code), ''), 'Transfer')
             ELSE ISNULL(NULLIF(RTRIM(s.suppliername), ''), CAST(pt.SupplierCode AS NVARCHAR(100)))
        END                                AS supplier,
        CASE WHEN RTRIM(pt.InvoiceSeries) = 'TI' THEN wh.store_name END AS source_store_name
    FROM sync.PurchaseTrans pt
    LEFT JOIN sync.Suppliers s
           ON s.tenant_id = pt.tenant_id
          AND s.store_id  = pt.store_id
          AND CAST(s.suppliercode AS VARCHAR(100)) = CAST(pt.SupplierCode AS VARCHAR(100))
    OUTER APPLY (
        SELECT TOP (1) w.store_code, w.store_name
        FROM dbo.stores w
        WHERE w.tenant_id = pt.tenant_id AND w.is_warehouse = 1
        ORDER BY w.store_code
    ) wh
    WHERE pt.tenant_id = @TenantId
      AND pt.store_id  = @StoreId
      AND pt.ProductCode = @ProductCode
    ORDER BY pt.grndate DESC;
END
GO

/* ===========================================================================
   6) stock.usp_SalesHistory   (Recent Sales panel)
   Faithful to sp_nmstock_get_sales + MRP column. Customer name from
   SaleInformation (joined on store + bill number + date).
   OUTPUT: date, bill_no, customer, qty, mrp, discount
   =========================================================================== */
IF OBJECT_ID(N'stock.usp_SalesHistory', N'P') IS NOT NULL DROP PROCEDURE stock.usp_SalesHistory;
GO
CREATE PROCEDURE stock.usp_SalesHistory
    @TenantId     UNIQUEIDENTIFIER,
    @StoreId      UNIQUEIDENTIFIER,
    @ProductCode  INT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP (50)
        CAST(psi.TransactionDate AS DATE)   AS [date],
        psi.Bnumber                         AS bill_no,
        si.CustomerName                     AS customer,
        ISNULL(psi.Quantity, 0)             AS qty,
        ISNULL(psi.MRP, 0)                  AS mrp,
        ISNULL(psi.DiscountPercentage, 0)   AS discount
    FROM sync.ProductSaleInformation psi
    LEFT JOIN sync.SaleInformation si
           ON si.tenant_id = psi.tenant_id
          AND si.store_id  = psi.store_id
          AND si.BNumber   = psi.Bnumber
          AND CAST(si.BillDate AS DATE) = CAST(psi.TransactionDate AS DATE)
    WHERE psi.tenant_id = @TenantId
      AND psi.store_id  = @StoreId
      AND psi.ProductCode = @ProductCode
      AND ISNULL(psi.TransactionValidity, 0) = 0
    ORDER BY psi.TransactionDate DESC;
END
GO

/* ===========================================================================
   7) stock.usp_BillItems   (Latest Bill panel)
   Faithful to sp_nmstock_get_bill_items; the SalesRep join is restored now that
   sync.SalesRep is synced (salesman name from SaleInformation.DeliverySalesRep).
   Adds line_no, sale_unit and amount for the UI.
   OUTPUT: line_no, salesman, product_name, sale_unit, qty, mrp, discount_pct, amount
   =========================================================================== */
IF OBJECT_ID(N'stock.usp_BillItems', N'P') IS NOT NULL DROP PROCEDURE stock.usp_BillItems;
GO
CREATE PROCEDURE stock.usp_BillItems
    @TenantId   UNIQUEIDENTIFIER,
    @StoreId    UNIQUEIDENTIFIER,
    @BillNo     NVARCHAR(50),
    @BillDate   DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;

    ;WITH BillMap AS
    (
        SELECT TOP (1)
            si.store_id, si.tenant_id, si.BNumber, si.BillNumber,
            CAST(si.BillDate AS DATE) AS BillDate,
            ISNULL(sr.Salesmanname, '-') AS SalesmanName
        FROM sync.SaleInformation si
        LEFT JOIN sync.SalesRep sr
               ON sr.store_id    = si.store_id
              AND sr.Salesmancode = si.DeliverySalesRep
        WHERE si.tenant_id = @TenantId
          AND si.store_id  = @StoreId
          AND si.BNumber   = @BillNo
          AND (@BillDate IS NULL OR CAST(si.BillDate AS DATE) = @BillDate)
        ORDER BY si.BillDate DESC
    )
    SELECT
        ROW_NUMBER() OVER (ORDER BY p.ProductName)    AS line_no,
        bm.SalesmanName                               AS salesman,
        p.ProductName                                 AS product_name,
        p.UnitDescription                             AS sale_unit,
        SUM(ISNULL(psi.Quantity, 0))                  AS qty,
        MAX(ISNULL(psi.MRP, 0))                       AS mrp,
        MAX(ISNULL(psi.DiscountPercentage, 0))        AS discount_pct,
        SUM(ISNULL(psi.Transactionamount, 0))         AS amount
    FROM BillMap bm
    INNER JOIN sync.ProductSaleInformation psi
            ON psi.tenant_id  = bm.tenant_id
           AND psi.store_id   = bm.store_id
           AND psi.BillNumber = bm.BillNumber
           AND psi.SeriesName = LEFT(bm.BNumber, 1)
           AND CAST(psi.TransactionDate AS DATE) = bm.BillDate
    INNER JOIN sync.Products p
            ON p.tenant_id   = psi.tenant_id
           AND p.store_id    = psi.store_id
           AND p.ProductCode = psi.ProductCode
    WHERE ISNULL(psi.TransactionValidity, 0) = 0
    GROUP BY bm.SalesmanName, p.ProductName, p.UnitDescription
    ORDER BY p.ProductName;
END
GO

/* ===========================================================================
   7b) stock.usp_ProductCore   (perf: batches + purchases + sales + movement
   in ONE call, so the client makes 1 round trip per store instead of 4.
   Bodies are copy-pasted from usp_BatchDetails / usp_PurchaseHistory /
   usp_SalesHistory / usp_MonthlyMovement — same output shapes, same order,
   returned as 4 result sets read via cursor.nextset()).
   =========================================================================== */
IF OBJECT_ID(N'stock.usp_ProductCore', N'P') IS NOT NULL DROP PROCEDURE stock.usp_ProductCore;
GO
CREATE PROCEDURE stock.usp_ProductCore
    @TenantId     UNIQUEIDENTIFIER,
    @StoreId      UNIQUEIDENTIFIER,
    @ProductCode  INT,
    @Months       INT = 3
AS
BEGIN
    SET NOCOUNT ON;

    -- Result set 1: batches (== stock.usp_BatchDetails) - every batch,
    -- zero-stock included; status/sort math lives in the frontend only.
    SELECT
        CAST(b.BatchCode AS VARCHAR(50))         AS batch_no,
        ISNULL(b.Stock, 0)                       AS stock,
        CAST(b.ExpiryDate AS DATE)                AS expiry_date,
        ISNULL(b.PurchasePrice, 0)               AS ptr,
        ISNULL(b.MRP, 0)                         AS mrp,
        CAST(b.GrnDate AS DATE)                   AS last_purchase_date,
        CAST(b.LastSaleDate AS DATE)              AS last_sale_date,
        DATEDIFF(DAY, b.GrnDate, GETDATE())      AS purchase_age_days,
        DATEDIFF(DAY, b.LastSaleDate, GETDATE()) AS sales_age_days
    FROM sync.Batches b
    WHERE b.tenant_id = @TenantId
      AND b.store_id  = @StoreId
      AND b.ProductCode = @ProductCode
    ORDER BY
        CASE WHEN ISNULL(b.Stock, 0) > 0 THEN 0 ELSE 1 END,
        b.ExpiryDate;

    -- Result set 2: purchases (== stock.usp_PurchaseHistory) — internal 'TI'
    -- transfers resolve to the tenant warehouse, not the colliding SupplierCode.
    SELECT TOP (15)
        CAST(pt.Grnnumber AS NVARCHAR(50)) AS grn_no,
        CAST(pt.grndate AS DATE)           AS [date],
        ISNULL(pt.stockreceived, 0)        AS qty,
        ISNULL(pt.FreeQty, 0)              AS free,
        ISNULL(pt.ProductDiscPercent, 0)   AS dis,
        ISNULL(pt.itemcost, 0)             AS cost,
        ISNULL(pt.purchaseprice, 0)        AS ptr,
        ISNULL(pt.mrp, 0)                  AS mrp,
        RTRIM(pt.InvoiceSeries)            AS invoice_series,
        CASE WHEN RTRIM(pt.InvoiceSeries) = 'TI' THEN 'transfer' ELSE 'supplier' END AS party_type,
        CASE WHEN RTRIM(pt.InvoiceSeries) = 'TI'
             THEN ISNULL(NULLIF(RTRIM(wh.store_code), ''), 'Transfer')
             ELSE ISNULL(NULLIF(RTRIM(s.suppliername), ''), CAST(pt.SupplierCode AS NVARCHAR(100)))
        END                                AS supplier,
        CASE WHEN RTRIM(pt.InvoiceSeries) = 'TI' THEN wh.store_name END AS source_store_name
    FROM sync.PurchaseTrans pt
    LEFT JOIN sync.Suppliers s
           ON s.tenant_id = pt.tenant_id
          AND s.store_id  = pt.store_id
          AND CAST(s.suppliercode AS VARCHAR(100)) = CAST(pt.SupplierCode AS VARCHAR(100))
    OUTER APPLY (
        SELECT TOP (1) w.store_code, w.store_name
        FROM dbo.stores w
        WHERE w.tenant_id = pt.tenant_id AND w.is_warehouse = 1
        ORDER BY w.store_code
    ) wh
    WHERE pt.tenant_id = @TenantId
      AND pt.store_id  = @StoreId
      AND pt.ProductCode = @ProductCode
    ORDER BY pt.grndate DESC;

    -- Result set 3: sales (== stock.usp_SalesHistory)
    SELECT TOP (50)
        CAST(psi.TransactionDate AS DATE)   AS [date],
        psi.Bnumber                         AS bill_no,
        si.CustomerName                     AS customer,
        ISNULL(psi.Quantity, 0)             AS qty,
        ISNULL(psi.MRP, 0)                  AS mrp,
        ISNULL(psi.DiscountPercentage, 0)   AS discount
    FROM sync.ProductSaleInformation psi
    LEFT JOIN sync.SaleInformation si
           ON si.tenant_id = psi.tenant_id
          AND si.store_id  = psi.store_id
          AND si.BNumber   = psi.Bnumber
          AND CAST(si.BillDate AS DATE) = CAST(psi.TransactionDate AS DATE)
    WHERE psi.tenant_id = @TenantId
      AND psi.store_id  = @StoreId
      AND psi.ProductCode = @ProductCode
      AND ISNULL(psi.TransactionValidity, 0) = 0
    ORDER BY psi.TransactionDate DESC;

    -- Result set 4: monthly movement (== stock.usp_MonthlyMovement)
    DECLARE @start DATE =
        DATEADD(MONTH, -(@Months - 1), DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1));

    ;WITH months AS
    (
        SELECT @start AS m
        UNION ALL
        SELECT DATEADD(MONTH, 1, m)
        FROM months
        WHERE m < DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)
    )
    SELECT
        FORMAT(mo.m, 'MMM yyyy')                 AS period,
        ISNULL(t.PurchaseQuantity, 0)            AS pur,
        ISNULL(t.SaleQuantity, 0)                AS sal,
        ISNULL(t.TransferInQuantity, 0)          AS tin,
        ISNULL(t.TransferOutQuantity, 0)         AS tout,
        ISNULL(t.AdjustmentQuantity, 0)          AS adj,
        ISNULL(t.StockInHand, 0)                 AS stk
    FROM months mo
    LEFT JOIN sync.ProductTrans t
           ON t.tenant_id = @TenantId
          AND t.store_id  = @StoreId
          AND t.ProductCode = @ProductCode
          AND YEAR(t.MonthOfStatistics)  = YEAR(mo.m)
          AND MONTH(t.MonthOfStatistics) = MONTH(mo.m)
    ORDER BY mo.m
    OPTION (MAXRECURSION 100);
END
GO

/* ===========================================================================
   8) stock.usp_MonthlyMovement   (Monthly Movement bar chart)
   Faithful to usp_GetProductTransTimelineChart; last @Months calendar months.
   OUTPUT (one row per month, oldest -> newest):
     period, pur, sal, tin, tout, adj, stk
   =========================================================================== */
IF OBJECT_ID(N'stock.usp_MonthlyMovement', N'P') IS NOT NULL DROP PROCEDURE stock.usp_MonthlyMovement;
GO
CREATE PROCEDURE stock.usp_MonthlyMovement
    @TenantId     UNIQUEIDENTIFIER,
    @StoreId      UNIQUEIDENTIFIER,
    @ProductCode  INT,
    @Months       INT = 4
AS
BEGIN
    SET NOCOUNT ON;

    -- Always emit exactly @Months month buckets (oldest -> newest), zero-filled
    -- for months that have no ProductTrans row, so the chart never collapses to
    -- the few months that happen to have data.
    DECLARE @start DATE =
        DATEADD(MONTH, -(@Months - 1), DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1));

    ;WITH months AS
    (
        SELECT @start AS m
        UNION ALL
        SELECT DATEADD(MONTH, 1, m)
        FROM months
        WHERE m < DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1)
    )
    SELECT
        FORMAT(mo.m, 'MMM yyyy')                 AS period,
        ISNULL(t.PurchaseQuantity, 0)            AS pur,
        ISNULL(t.SaleQuantity, 0)                AS sal,
        ISNULL(t.TransferInQuantity, 0)          AS tin,
        ISNULL(t.TransferOutQuantity, 0)         AS tout,
        ISNULL(t.AdjustmentQuantity, 0)          AS adj,
        ISNULL(t.StockInHand, 0)                 AS stk
    FROM months mo
    LEFT JOIN sync.ProductTrans t
           ON t.tenant_id = @TenantId
          AND t.store_id  = @StoreId
          AND t.ProductCode = @ProductCode
          AND YEAR(t.MonthOfStatistics)  = YEAR(mo.m)
          AND MONTH(t.MonthOfStatistics) = MONTH(mo.m)
    ORDER BY mo.m
    OPTION (MAXRECURSION 100);
END
GO
