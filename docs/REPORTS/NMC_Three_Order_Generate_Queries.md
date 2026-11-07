# NMC three order-generation queries

Store: NMC, store code 7. Comparison as-of: 2026-10-25 12:21.
Queries 1 and 3 run on OrderNMC. Query 2 reads NEXORA_PLATFORM sync tables.

These are the three generators behind `NMC_Three_Way_Order_Battle_2026-10-25.xlsx`.
Query 1 and query 3 return the pack quantity. Query 2 loads the inputs;
`decision_rules.evaluate` calculates the Nexora pack quantity. There is no third SQL that emits it.

## 1. LE_Order

Source: `backend/modules/legacy_order/sql/order_local.sql`, executed by
`order_process.fetch_source_data` in local mode against central OrderNMC.

NMC parameters from the comparison:

```sql
DECLARE @minday int = 13;
DECLARE @maxday int = 18;
DECLARE @storename varchar(50) = N'NMC';
DECLARE @storecode int = 7;
DECLARE @ODATA date = '2026-07-27';
DECLARE @status int = 0;
DECLARE @recencydays int = 15;
```

`@ODATA` is the as-of date minus 90 days. `@recencydays` 15 is the `LEGACY_RECENCY_DAYS` default.

```sql
WITH SalesQuantity AS (SELECT ps.productcode, SUM(ps.quantity) AS slsqty, COUNT(DISTINCT ps.ID) AS Frequence, ps.storename FROM ProductSaleInformation ps INNER JOIN products p ON ps.Productcode = p.productcode AND ps.StoreName = p.StoreName WHERE ps.Transactiondate >= @ODATA AND ps.quantity > 0 AND ps.SeriesTransID = 1 AND ps.transactionvalidity = 0 AND p.isactive = 1 AND ps.DontConsiderInOrder = 0 AND ps.storename = @storename GROUP BY ps.productcode, ps.storename), MaxSalesQty AS (SELECT Productcode, MAX(Quantity) AS MaxSalesQtyInBill FROM ProductSaleInformation WHERE SeriesTransID = 1 AND transactionvalidity = 0 AND Transactiondate >= @ODATA AND storename = @storename GROUP BY Productcode), ProductSaleInfo AS (SELECT p.productcode, p.productname, p.TotalStock, p.SaleUnit, sq.slsqty, p.PurchasePrice, p.MRP, p.UnitDescription, p.SubLocation, p.producttype, CEILING(sq.slsqty / NULLIF(sq.Frequence, 0)) AS AvgSalesQty, m.MaxSalesQtyInBill, GETDATE() AS wanteddate, p.StoreName, @storecode AS storecode, CONVERT(VARCHAR(8), GETDATE(), 112) + RIGHT('0' + CONVERT(VARCHAR(2), DATEPART(HOUR, GETDATE())), 2) + RIGHT('0' + CONVERT(VARCHAR(2), DATEPART(MINUTE, GETDATE())), 2) + RIGHT('0' + CONVERT(VARCHAR(2), DATEPART(SECOND, GETDATE())), 2) AS OrderID, CASE WHEN CEILING((sq.slsqty / 90.0) * @minday) < CEILING(sq.slsqty / NULLIF(sq.Frequence, 0)) THEN CEILING(sq.slsqty / NULLIF(sq.Frequence, 0)) ELSE CEILING((sq.slsqty / 90.0) * @minday) END AS minqty, CASE WHEN CEILING((sq.slsqty / 90.0) * @maxday) < m.MaxSalesQtyInBill THEN m.MaxSalesQtyInBill ELSE CEILING((sq.slsqty / 90.0) * @maxday) END AS maxqty, CASE WHEN CEILING((sq.slsqty / 90.0) * @minday) <= maxQtyInPeriod.Maxsaleqty THEN 'Single Day Sales Greater than MinQty' ELSE 'Regular Order Based Min & Max' END AS Wantedtype, sq.Frequence, l.lastsaledate, l.LastReceivedDate FROM products p INNER JOIN SalesQuantity sq ON p.productcode = sq.productcode AND p.storename = sq.StoreName LEFT JOIN MaxSalesQty m ON p.productcode = m.Productcode LEFT JOIN (SELECT pt.Productcode, MAX(pt.LastBillDate) AS lastsaledate, MAX(pt.LastgrnDate) AS LastReceivedDate, pt.StoreName FROM ProductTrans pt WHERE pt.lastbilldate >= DATEADD(day, 0 - @recencydays, GETDATE()) AND pt.LastBillDate IS NOT NULL AND pt.storename = @storename GROUP BY pt.Productcode, pt.StoreName) l ON p.productcode = l.Productcode LEFT JOIN (SELECT Productcode, MAX(sales) AS Maxsaleqty FROM (SELECT SUM(Quantity) AS sales, Productcode FROM ProductSaleInformation WHERE SeriesTransID = 1 AND transactionvalidity = 0 AND Transactiondate >= @ODATA AND storename = @storename GROUP BY Productcode) AS sales_summary GROUP BY Productcode) maxQtyInPeriod ON p.productcode = maxQtyInPeriod.Productcode), MaxSaleInfo AS (SELECT T.Productcode, T.Maxsaleqty, T.Transactiondate, T.storename FROM (SELECT Productcode, MAX(sales) AS Maxsaleqty, Transactiondate, storename FROM (SELECT SUM(Quantity) AS sales, Productcode, Transactiondate, psi.storename, ROW_NUMBER() OVER(PARTITION BY Productcode ORDER BY SUM(Quantity) DESC) AS rn FROM ProductSaleInformation psi WHERE psi.SeriesTransID = 1 AND psi.transactionvalidity = 0 AND psi.Transactiondate > @ODATA AND psi.storename = @storename GROUP BY Productcode, Transactiondate, psi.storename) subquery WHERE rn = 1 GROUP BY Productcode, Transactiondate, storename) T) SELECT ps.productcode, ps.productname, ps.minqty, ps.maxqty, ps.TotalStock, ps.slsqty, ps.producttype, ps.lastsaledate, ps.LastReceivedDate, m.Maxsaleqty, m.Transactiondate, ps.wanteddate, ps.StoreName, @storecode AS storecode, ps.OrderID, ps.SaleUnit, ps.PurchasePrice, ps.MRP, ps.UnitDescription, ps.SubLocation, CASE WHEN ps.TotalStock = 0 AND ROUND(((ps.maxqty - ps.TotalStock) / NULLIF(ps.SaleUnit, 0)), 0) = 0 THEN 'Rare Moment' WHEN CEILING(CASE WHEN ps.minqty < ps.AvgSalesQty THEN ps.AvgSalesQty ELSE ps.minqty END) < m.Maxsaleqty THEN 'Min & Max Based MaxsaleQTY' WHEN ps.slsqty = m.Maxsaleqty AND m.Maxsaleqty = CASE WHEN ps.minqty < ps.AvgSalesQty THEN ps.AvgSalesQty ELSE ps.minqty END AND ps.Frequence = 1 THEN 'Once Sold Last 90 days' ELSE 'Regular Order Based Min & Max' END AS Wantedtype, CASE WHEN ps.producttype = 0 THEN 0 ELSE 1 END AS productType, CASE WHEN ps.producttype = 0 THEN 'Non Pharma' ELSE 'Pharma' END AS producttypename, ps.Frequence, ps.AvgSalesQty, ps.MaxSalesQtyInBill, CASE WHEN ps.TotalStock = 0 AND (ps.maxqty - ps.TotalStock) <= 0 THEN 1 WHEN ps.SaleUnit > 0 THEN CEILING((ps.maxqty - ps.TotalStock) / ps.SaleUnit) ELSE 0 END AS Orderqty, @status AS status FROM ProductSaleInfo ps LEFT JOIN MaxSaleInfo m ON ps.productcode = m.Productcode AND ps.StoreName = m.StoreName WHERE ps.lastsaledate >= DATEADD(day, 0 - @recencydays, GETDATE()) AND (ps.maxqty - ps.TotalStock) / NULLIF(ps.SaleUnit, 0) > 0 AND ps.minqty > ps.TotalStock AND ps.lastsaledate >= ps.LastReceivedDate AND ps.StoreName = @storename UNION ALL SELECT ps.productcode, ps.productname, 1 AS minqty, 1 AS maxqty, ps.TotalStock, ps.slsqty, ps.producttype, ps.lastsaledate, ps.LastReceivedDate, m.Maxsaleqty, m.Transactiondate, ps.wanteddate, ps.StoreName, ps.storecode, ps.OrderID, ps.SaleUnit, ps.PurchasePrice, ps.MRP, ps.UnitDescription, ps.SubLocation, 'Additional Row' AS Wantedtype, CASE WHEN ps.producttype = 0 THEN 0 ELSE 1 END AS productType2, CASE WHEN ps.producttype = 0 THEN 'Non Pharma' ELSE 'Pharma' END AS producttypename, ps.Frequence, ps.AvgSalesQty, ps.MaxSalesQtyInBill, 1 AS Orderqty, @status AS status FROM ProductSaleInfo ps LEFT JOIN MaxSaleInfo m ON ps.productcode = m.Productcode WHERE ps.TotalStock <= 1 AND ps.minqty <= 1 AND ps.Frequence > 1 AND ps.slsqty > 1 AND ps.lastsaledate >= DATEADD(day, 0 - @recencydays, GETDATE()) AND ps.lastsaledate > ps.LastReceivedDate AND ps.StoreName = @storename AND NOT EXISTS (SELECT 1 FROM ProductSaleInfo WHERE productcode = ps.productcode AND (ps.maxqty - ps.TotalStock) / NULLIF(ps.SaleUnit, 0) > 0 AND ps.minqty > ps.TotalStock AND storename = @storename) ORDER BY ps.productname;
```

After the SELECT, the live caller zeros Additional Row. That statement writes
`OrderManagement`. It was not executed for the comparison. The workbook uses
that caller result: SQL Orderqty 1 becomes order quantity 0.

```sql
UPDATE OrderManagement
SET OrderQty = 0, OrgOrderQty = 0, Status = 2, Remarks = 'Additional'
WHERE StoreName = N'NMC' AND WantedType = 'Additional Row';
```

Main-line quantity: `CEILING((maxqty - TotalStock) / SaleUnit)` when SaleUnit is positive.
`maxqty` is the larger of `CEILING((90-day qty / 90) * 18)` and the largest single sale line.
The row is kept only when `minqty > TotalStock`, pack demand is positive, last bill date
is inside 15 days, and last bill date is greater than or equal to `LastGrnDate`.
A NULL `LastGrnDate` drops the row.

## 2. Nexora_OR

Source: `backend/modules/procurement/decision_repository.py` `load_source`, then
`backend/modules/procurement/decision_rules.py` `evaluate`.

NMC comparison settings passed to `evaluate`: rolling 90, min 13, max 18, recency 10.
Pending receivable, in transit, and reserved were 0. On that run, latest `StockInHand`
equalled `TotalStock` for every evaluated product.

```sql
-- Nexora_OR does not calculate OrderQty in SQL.
-- This is the order-input SELECT from decision_repository.load_source.
-- decision_rules.evaluate turns each returned row into a pack quantity.
-- Tables are NEXORA_PLATFORM sync.*, not OrderNMC.
-- Placeholder order:
--   sales: tenant_id, store_id, cutoff (as-of date minus rolling_days)
--   last sale: tenant_id, store_id
--   any GRN: tenant_id, store_id
--   products: tenant_id, store_id

WITH sales AS (
    SELECT psi.ProductCode,
           CAST(psi.TransactionDate AS DATE) AS d,
           CAST(psi.SeriesName AS VARCHAR(10)) + '|'
             + CAST(psi.BillNumber AS VARCHAR(50)) + '|'
             + CONVERT(VARCHAR(8), psi.TransactionDate, 112) AS bill_key,
           ISNULL(psi.Quantity, 0) AS qty
    FROM sync.ProductSaleInformation psi
    WHERE psi.tenant_id = ?
      AND psi.store_id = ?
      AND ISNULL(psi.TransactionValidity, 0) = 0
      AND psi.SeriesTransID = 1
      AND ISNULL(psi.DontConsiderInOrder, 0) = 0
      AND psi.TransactionDate >= ?
),
per_day  AS (SELECT ProductCode, d, SUM(qty) AS q FROM sales GROUP BY ProductCode, d),
per_bill AS (SELECT ProductCode, bill_key, SUM(qty) AS q FROM sales GROUP BY ProductCode, bill_key),
agg AS (
    SELECT ProductCode,
           SUM(qty) AS window_sales_qty,
           COUNT(DISTINCT bill_key) AS billing_frequency
    FROM sales GROUP BY ProductCode
),
md AS (SELECT ProductCode, MAX(q) AS max_day_sale_qty FROM per_day GROUP BY ProductCode),
mb AS (SELECT ProductCode, MAX(q) AS max_bill_qty FROM per_bill GROUP BY ProductCode),
ml AS (SELECT ProductCode, MAX(qty) AS max_line_sale_qty FROM sales GROUP BY ProductCode),
ls AS (
    SELECT ProductCode, MAX(TransactionDate) AS last_sale_date
    FROM sync.ProductSaleInformation
    WHERE tenant_id = ? AND store_id = ?
      AND ISNULL(TransactionValidity, 0) = 0
      AND SeriesTransID = 1
    GROUP BY ProductCode
),
grn AS (
    SELECT ProductCode, MAX(grndate) AS last_received_date
    FROM sync.PurchaseTrans
    WHERE tenant_id = ? AND store_id = ?
    GROUP BY ProductCode
)
SELECT
    CAST(p.ProductCode AS VARCHAR(100)) AS product_code,
    p.ProductName AS product_name,
    p.UnitDescription AS unit,
    CAST(ISNULL(p.isActive, 1) AS BIT) AS is_active,
    CAST(0 AS BIT) AS dont_consider,
    CAST(ISNULL(agg.window_sales_qty, 0) AS DECIMAL(18,3)) AS window_sales_qty,
    CAST(ISNULL(md.max_day_sale_qty, 0) AS DECIMAL(18,3)) AS max_day_sale_qty,
    CAST(ISNULL(mb.max_bill_qty, 0) AS DECIMAL(18,3)) AS max_bill_qty,
    CAST(ISNULL(ml.max_line_sale_qty, 0) AS DECIMAL(18,3)) AS max_line_sale_qty,
    CAST(ISNULL(agg.billing_frequency, 0) AS INT) AS billing_frequency,
    CAST(COALESCE((
        SELECT TOP (1) pt.StockInHand
        FROM sync.ProductTrans pt
        WHERE pt.store_id = p.store_id
          AND pt.ProductCode = p.ProductCode
        ORDER BY pt.MonthOfStatistics DESC
    ), p.TotalStock, 0) AS DECIMAL(18,3)) AS current_stock,
    CAST(p.SaleUnit AS DECIMAL(18,3)) AS sale_unit,
    ls.last_sale_date,
    grn.last_received_date
FROM sync.Products p
LEFT JOIN agg ON agg.ProductCode = p.ProductCode
LEFT JOIN md  ON md.ProductCode  = p.ProductCode
LEFT JOIN mb  ON mb.ProductCode  = p.ProductCode
LEFT JOIN ml  ON ml.ProductCode  = p.ProductCode
LEFT JOIN ls  ON ls.ProductCode  = p.ProductCode
LEFT JOIN grn ON grn.ProductCode = p.ProductCode
WHERE p.tenant_id = ? AND p.store_id = ?
  AND ISNULL(p.isActive, 1) = 1;
```

Quantity rules applied in Python to each source row:

```text
avg = window_sales_qty / 90
stock = current_stock + pending_receivable + in_transit - reserved
cover = stock / avg
min_floor = MAX(CEIL(avg * 13), CEIL(window_sales_qty / billing_frequency))

Exclude when inactive, dont_consider, avg <= 0,
  last sale is missing or older than 10 days,
  or a GRN exists and last sale is strictly before that GRN.
A missing GRN does not exclude.

Include when cover < 13 OR stock < min_floor.
Otherwise, if stock <= 1 and min_floor <= 1 and billing_frequency > 1
  and window_sales_qty > 1, order 1 pack (rare-mover top-up).
Otherwise exclude.

gross = MAX(avg * 18, max_day_sale_qty, max_bill_qty, max_line_sale_qty)
net = gross - stock
OrderQty = CEILING(net / SaleUnit) when SaleUnit > 0
OrderQty = CEILING(net) when SaleUnit is missing or not positive
```

## 3. New_Nexora_Order

Rule Book query executed read-only on OrderNMC for store NMC.
`@ConfirmedPending` was empty. `@StoreName` is NMC. The rest of the statement
is the supplied Rule Book query.

```sql
/* Rule book order generation — one store, normal auto-order list.
   Off the list: no valid sale in 15 days, last valid sale strictly before
   the latest IV receipt, SaleUnit null/<=0, net <= 0.
   Confirmed pending has no verified column. Load @ConfirmedPending first.
   Empty table = pending 0. */
DECLARE @StoreName varchar(50) = N'NMC';
DECLARE @AsOf      datetime    = GETDATE();
DECLARE @From      date        = DATEADD(day, -90, CAST(@AsOf AS date));
DECLARE @Recency   datetime    = DATEADD(day, -15, @AsOf);

DECLARE @ConfirmedPending TABLE (
    productcode varchar(50)  NOT NULL PRIMARY KEY,
    qty         decimal(18,3) NOT NULL
);
/* INSERT confirmed qty - received qty here.
   Confirmed means exported/placed, after cancels and valid reversals.
   Drafts, failed exports, and unexported lines are not pending.
   The NMC comparison left this table empty. Pending 0 is an assumption. */

WITH sales AS (
    SELECT ps.productcode,
           ps.quantity,
           CAST(ps.Transactiondate AS date) AS sale_day,
           ps.BNumber AS bill_no
    FROM ProductSaleInformation ps
    INNER JOIN products p
        ON p.productcode = ps.productcode
       AND p.StoreName   = ps.StoreName
    WHERE ps.StoreName = @StoreName
      AND ps.Transactiondate >= @From
      AND ps.quantity > 0
      AND ps.SeriesTransID = 1
      AND ps.transactionvalidity = 0
      AND ps.DontConsiderInOrder = 0
      AND p.isactive = 1
),
per_day AS (
    SELECT productcode, sale_day, SUM(quantity) AS day_qty
    FROM sales
    GROUP BY productcode, sale_day
),
per_bill AS (
    SELECT productcode, bill_no, sale_day, SUM(quantity) AS bill_qty
    FROM sales
    GROUP BY productcode, bill_no, sale_day
),
agg AS (
    SELECT s.productcode,
           SUM(s.quantity) AS window_qty,
           COUNT(DISTINCT CONCAT(s.bill_no, '|', CONVERT(char(8), s.sale_day, 112))) AS bill_count
    FROM sales s
    GROUP BY s.productcode
),
limits AS (
    SELECT a.productcode,
           a.window_qty,
           a.bill_count,
           a.window_qty / 90.0 AS avg_daily,
           a.window_qty / NULLIF(a.bill_count, 0) AS avg_bill,
           (SELECT MAX(d.day_qty)  FROM per_day  d WHERE d.productcode = a.productcode) AS max_day,
           (SELECT MAX(b.bill_qty) FROM per_bill b WHERE b.productcode = a.productcode) AS max_bill
    FROM agg a
),
last_sale AS (
    SELECT ps.productcode, MAX(ps.Transactiondate) AS last_sale
    FROM ProductSaleInformation ps
    WHERE ps.StoreName = @StoreName
      AND ps.quantity > 0
      AND ps.SeriesTransID = 1
      AND ps.transactionvalidity = 0
      AND ps.DontConsiderInOrder = 0
    GROUP BY ps.productcode
),
last_receipt AS (
    SELECT pt.productcode, MAX(pt.Grndate) AS last_receipt
    FROM Purchasetrans pt
    WHERE pt.StoreName = @StoreName
      AND pt.InvoiceSeries = 'IV'
    GROUP BY pt.productcode
)
SELECT p.productcode,
       p.productname,
       p.TotalStock,
       p.SaleUnit,
       l.window_qty,
       l.avg_daily,
       l.max_day,
       l.max_bill,
       l.avg_bill,
       ISNULL(cp.qty, 0) AS confirmed_pending,
       v.gross_qty,
       v.net_qty,
       CEILING(v.net_qty / p.SaleUnit) AS OrderQty
FROM limits l
INNER JOIN products p
    ON p.productcode = l.productcode
   AND p.StoreName   = @StoreName
INNER JOIN last_sale ls
    ON ls.productcode = l.productcode
LEFT JOIN last_receipt lr
    ON lr.productcode = l.productcode
LEFT JOIN @ConfirmedPending cp
    ON cp.productcode = l.productcode
CROSS APPLY (
    SELECT
        CASE
            WHEN ISNULL(l.max_day, 0) >= ISNULL(l.max_bill, 0)
             AND ISNULL(l.max_day, 0) >= ISNULL(l.avg_bill, 0)
             AND ISNULL(l.max_day, 0) >= l.avg_daily * 18
                THEN CAST(l.max_day AS decimal(18,4))
            WHEN ISNULL(l.max_bill, 0) >= ISNULL(l.avg_bill, 0)
             AND ISNULL(l.max_bill, 0) >= l.avg_daily * 18
                THEN CAST(l.max_bill AS decimal(18,4))
            WHEN ISNULL(l.avg_bill, 0) >= l.avg_daily * 18
                THEN CAST(l.avg_bill AS decimal(18,4))
            ELSE CAST(l.avg_daily * 18 AS decimal(18,4))
        END AS gross_qty
) g
CROSS APPLY (
    SELECT g.gross_qty,
           g.gross_qty - ISNULL(p.TotalStock, 0) - ISNULL(cp.qty, 0) AS net_qty
) v
WHERE p.isactive = 1
  AND p.SaleUnit > 0
  AND ls.last_sale >= @Recency
  AND (lr.last_receipt IS NULL OR ls.last_sale >= lr.last_receipt)
  AND v.net_qty > 0
ORDER BY p.productname;
```

Quantity: gross is the maximum of `avg_daily * 18`, max day, max bill, and average bill.
Net is gross minus `TotalStock` minus confirmed pending.
`OrderQty = CEILING(net / SaleUnit)`.
A product is returned only when SaleUnit is positive, the last valid sale is inside 15 days,
the last valid sale is not strictly before the latest IV receipt, and net is positive.
A NULL IV receipt does not drop the product.
