-- Warehouse order query -- a faithful copy of order_local.sql with exactly the
-- changes a WAREHOUSE (e.g. NMW) needs, so the retail order_local.sql/
-- order_remote.sql stay byte-for-byte unchanged and no retail store can regress.
--
-- Three warehouse-specific differences from order_local.sql (and nothing else):
--   1. DEMAND BASIS: count retail billing (SeriesTransID=1, i.e. series 'D' at
--      the warehouse) PLUS Transfer-Out to branches (SeriesName='TO'). A
--      warehouse's real demand is what it ships to stores; the retail-only
--      filter ignored ~1/3 of it and systematically under-ordered.
--   2. RECENCY SOURCE: lastsaledate is the MAX real D+TO TransactionDate from
--      ProductSaleInformation -- NOT ProductTrans.LastBillDate, which only
--      tracks retail bills (verified on live data) and would still drop
--      transfer-only movers even after (1).
--   3. CONFIGURABLE RECENCY: the "sold in the last N days" / "sold since the
--      last GRN" gates use a bound recency parameter (retail hardcodes 10). A warehouse
--      despatches a given line less often than a shop sells it, so 10 days is
--      too aggressive; the service defaults warehouses to a wider window.
--
-- Everything else -- the per-bill MinQty floor, the single-line spike floor
-- (MaxSalesQtyInBill), maxqty, the Additional Row rare-mover top-up, the
-- sold-since-GRN gate, pack rounding by SaleUnit, and every output column and
-- its name -- is identical to order_local.sql so order_process.COLUMN_MAP maps
-- the result set exactly as it does for the retail query.
WITH SalesQuantity AS (
    SELECT ps.productcode, SUM(ps.quantity) AS slsqty,
           COUNT(DISTINCT ps.ID) AS Frequence, ps.storename
    FROM ProductSaleInformation ps
    INNER JOIN products p ON ps.Productcode = p.productcode AND ps.StoreName = p.StoreName
    WHERE ps.Transactiondate >= @ODATA AND ps.quantity > 0
      AND (ps.SeriesTransID = 1 OR ps.SeriesName = 'TO')
      AND ps.transactionvalidity = 0 AND p.isactive = 1
      -- Transfer-Out (TO) rows carry DontConsiderInOrder = NULL, and "= 0"
      -- rejects NULL (NULL = 0 is UNKNOWN), which silently dropped every
      -- transfer from demand. ISNULL(..,0) keeps NULL/0 (consider it) while
      -- still honouring a genuine do-not-order flag of 1.
      AND ISNULL(ps.DontConsiderInOrder, 0) = 0 AND ps.storename = @storename
    GROUP BY ps.productcode, ps.storename
),
MaxSalesQty AS (
    SELECT Productcode, MAX(Quantity) AS MaxSalesQtyInBill
    FROM ProductSaleInformation
    WHERE (SeriesTransID = 1 OR SeriesName = 'TO') AND transactionvalidity = 0
      AND Transactiondate >= @ODATA AND storename = @storename
    GROUP BY Productcode
),
ProductSaleInfo AS (
    SELECT p.productcode, p.productname, p.TotalStock, p.SaleUnit, sq.slsqty,
           p.PurchasePrice, p.MRP, p.UnitDescription, p.SubLocation, p.producttype,
           CEILING(sq.slsqty / NULLIF(sq.Frequence, 0)) AS AvgSalesQty,
           m.MaxSalesQtyInBill, GETDATE() AS wanteddate, p.StoreName,
           @storecode AS storecode,
           CONVERT(VARCHAR(8), GETDATE(), 112)
             + RIGHT('0' + CONVERT(VARCHAR(2), DATEPART(HOUR, GETDATE())), 2)
             + RIGHT('0' + CONVERT(VARCHAR(2), DATEPART(MINUTE, GETDATE())), 2)
             + RIGHT('0' + CONVERT(VARCHAR(2), DATEPART(SECOND, GETDATE())), 2) AS OrderID,
           CASE WHEN CEILING((sq.slsqty / 90.0) * @minday) < CEILING(sq.slsqty / NULLIF(sq.Frequence, 0))
                THEN CEILING(sq.slsqty / NULLIF(sq.Frequence, 0))
                ELSE CEILING((sq.slsqty / 90.0) * @minday) END AS minqty,
           CASE WHEN CEILING((sq.slsqty / 90.0) * @maxday) < m.MaxSalesQtyInBill
                THEN m.MaxSalesQtyInBill
                ELSE CEILING((sq.slsqty / 90.0) * @maxday) END AS maxqty,
           CASE WHEN CEILING((sq.slsqty / 90.0) * @minday) <= maxQtyInPeriod.Maxsaleqty
                THEN 'Single Day Sales Greater than MinQty'
                ELSE 'Regular Order Based Min & Max' END AS Wantedtype,
           sq.Frequence, l.lastsaledate, l.LastReceivedDate
    FROM products p
    INNER JOIN SalesQuantity sq ON p.productcode = sq.productcode AND p.storename = sq.StoreName
    LEFT JOIN MaxSalesQty m ON p.productcode = m.Productcode
    LEFT JOIN (
        -- lastsaledate from the real D+TO transactions (ProductTrans.LastBillDate
        -- is retail-only); LastReceivedDate = last GRN over all history.
        SELECT sd.Productcode, sd.lastsaledate, gr.LastReceivedDate
        FROM (
            SELECT ps2.Productcode, MAX(ps2.Transactiondate) AS lastsaledate
            FROM ProductSaleInformation ps2
            WHERE ps2.storename = @storename AND ps2.transactionvalidity = 0
              AND ps2.Quantity > 0 AND (ps2.SeriesTransID = 1 OR ps2.SeriesName = 'TO')
              AND ps2.Transactiondate >= DATEADD(day, 0 - (@recencydays + 10), GETDATE())
            GROUP BY ps2.Productcode
        ) sd
        LEFT JOIN (
            SELECT pt.Productcode, MAX(pt.LastgrnDate) AS LastReceivedDate
            FROM ProductTrans pt WHERE pt.storename = @storename
            GROUP BY pt.Productcode
        ) gr ON gr.Productcode = sd.Productcode
    ) l ON p.productcode = l.Productcode
    LEFT JOIN (
        SELECT Productcode, MAX(sales) AS Maxsaleqty
        FROM (
            SELECT SUM(Quantity) AS sales, Productcode
            FROM ProductSaleInformation
            WHERE (SeriesTransID = 1 OR SeriesName = 'TO') AND transactionvalidity = 0
              AND Transactiondate >= @ODATA AND storename = @storename
            GROUP BY Productcode
        ) AS sales_summary
        GROUP BY Productcode
    ) maxQtyInPeriod ON p.productcode = maxQtyInPeriod.Productcode
),
MaxSaleInfo AS (
    SELECT T.Productcode, T.Maxsaleqty, T.Transactiondate, T.storename
    FROM (
        SELECT Productcode, MAX(sales) AS Maxsaleqty, Transactiondate, storename
        FROM (
            SELECT SUM(Quantity) AS sales, Productcode, Transactiondate, psi.storename,
                   ROW_NUMBER() OVER(PARTITION BY Productcode ORDER BY SUM(Quantity) DESC) AS rn
            FROM ProductSaleInformation psi
            WHERE (psi.SeriesTransID = 1 OR psi.SeriesName = 'TO') AND psi.transactionvalidity = 0
              AND psi.Transactiondate > @ODATA AND psi.storename = @storename
            GROUP BY Productcode, Transactiondate, psi.storename
        ) subquery
        WHERE rn = 1
        GROUP BY Productcode, Transactiondate, storename
    ) T
)
SELECT ps.productcode, ps.productname, ps.minqty, ps.maxqty, ps.TotalStock, ps.slsqty,
       ps.producttype, ps.lastsaledate, ps.LastReceivedDate, m.Maxsaleqty, m.Transactiondate,
       ps.wanteddate, ps.StoreName, @storecode AS storecode, ps.OrderID, ps.SaleUnit,
       ps.PurchasePrice, ps.MRP, ps.UnitDescription, ps.SubLocation,
       CASE WHEN ps.TotalStock = 0 AND ROUND(((ps.maxqty - ps.TotalStock) / NULLIF(ps.SaleUnit, 0)), 0) = 0 THEN 'Rare Moment'
            WHEN CEILING(CASE WHEN ps.minqty < ps.AvgSalesQty THEN ps.AvgSalesQty ELSE ps.minqty END) < m.Maxsaleqty THEN 'Min & Max Based MaxsaleQTY'
            WHEN ps.slsqty = m.Maxsaleqty AND m.Maxsaleqty = CASE WHEN ps.minqty < ps.AvgSalesQty THEN ps.AvgSalesQty ELSE ps.minqty END AND ps.Frequence = 1 THEN 'Once Sold Last 90 days'
            ELSE 'Regular Order Based Min & Max' END AS Wantedtype,
       CASE WHEN ps.producttype = 0 THEN 0 ELSE 1 END AS productType,
       CASE WHEN ps.producttype = 0 THEN 'Non Pharma' ELSE 'Pharma' END AS producttypename,
       ps.Frequence, ps.AvgSalesQty, ps.MaxSalesQtyInBill,
       CASE WHEN ps.TotalStock = 0 AND (ps.maxqty - ps.TotalStock) <= 0 THEN 1
            WHEN ps.SaleUnit > 0 THEN CEILING((ps.maxqty - ps.TotalStock) / ps.SaleUnit)
            ELSE 0 END AS Orderqty,
       @status AS status
FROM ProductSaleInfo ps
LEFT JOIN MaxSaleInfo m ON ps.productcode = m.Productcode AND ps.StoreName = m.StoreName
WHERE ps.lastsaledate >= DATEADD(day, 0 - @recencydays, GETDATE())
  AND (ps.maxqty - ps.TotalStock) / NULLIF(ps.SaleUnit, 0) > 0
  AND ps.minqty > ps.TotalStock
  AND ps.lastsaledate >= ps.LastReceivedDate
  AND ps.StoreName = @storename
UNION ALL
SELECT ps.productcode, ps.productname, 1 AS minqty, 1 AS maxqty, ps.TotalStock, ps.slsqty,
       ps.producttype, ps.lastsaledate, ps.LastReceivedDate, m.Maxsaleqty, m.Transactiondate,
       ps.wanteddate, ps.StoreName, ps.storecode, ps.OrderID, ps.SaleUnit,
       ps.PurchasePrice, ps.MRP, ps.UnitDescription, ps.SubLocation,
       'Additional Row' AS Wantedtype,
       CASE WHEN ps.producttype = 0 THEN 0 ELSE 1 END AS productType2,
       CASE WHEN ps.producttype = 0 THEN 'Non Pharma' ELSE 'Pharma' END AS producttypename,
       ps.Frequence, ps.AvgSalesQty, ps.MaxSalesQtyInBill, 1 AS Orderqty, @status AS status
FROM ProductSaleInfo ps
LEFT JOIN MaxSaleInfo m ON ps.productcode = m.Productcode
WHERE ps.TotalStock <= 1 AND ps.minqty <= 1 AND ps.Frequence > 1 AND ps.slsqty > 1
  AND ps.lastsaledate >= DATEADD(day, 0 - @recencydays, GETDATE())
  AND ps.lastsaledate > ps.LastReceivedDate AND ps.StoreName = @storename
  AND NOT EXISTS (
      SELECT 1 FROM ProductSaleInfo
      WHERE productcode = ps.productcode
        AND (ps.maxqty - ps.TotalStock) / NULLIF(ps.SaleUnit, 0) > 0
        AND ps.minqty > ps.TotalStock AND storename = @storename
  )
ORDER BY productname;
