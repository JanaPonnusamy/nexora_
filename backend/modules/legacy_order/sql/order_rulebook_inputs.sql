-- Rule-book order inputs (see rulebook_order.py): one row per active product
-- of the store that had a valid demand line in the window. Pure read of the
-- central OrderNMC copy -- the quantity is decided in Python by the Procurement
-- rule book (quantity_profile_t), not here.
--
-- Valid demand line (rule book, eligibility):
--   TransactionValidity = 0, Quantity > 0, DontConsiderInOrder not set,
--   retail billing (SeriesTransID = 1), plus Transfer-Out (SeriesName 'TO')
--   for a warehouse store -- the warehouse demand ruling of 2026-10-07.
-- Bill metrics sum the product's lines on one bill first (series + bill no);
-- max day is the product's total on one calendar date.
WITH v AS (
    SELECT ps.ProductCode, ps.SeriesName, ps.Bnumber, ps.ID, ps.Quantity, ps.TransactionDate,
           CAST(ps.TransactionDate AS date) AS d
    FROM ProductSaleInformation ps WITH (NOLOCK)
    WHERE ps.StoreName = @storename
      AND ps.TransactionDate >= @ODATA
      AND ps.Quantity > 0
      AND ps.TransactionValidity = 0
      AND ISNULL(ps.DontConsiderInOrder, 0) = 0
      AND (ps.SeriesTransID = 1 OR (@warehouse = 1 AND ps.SeriesName = 'TO'))
),
agg AS (
    SELECT ProductCode,
           SUM(Quantity) AS window_qty,
           COUNT(DISTINCT CONCAT(RTRIM(SeriesName), '|', RTRIM(Bnumber))) AS bill_frequency,
           COUNT(DISTINCT ID) AS line_frequency,
           MAX(TransactionDate) AS last_sale
    FROM v
    GROUP BY ProductCode
),
bills AS (
    SELECT ProductCode, MAX(q) AS max_bill_qty
    FROM (SELECT ProductCode, SUM(Quantity) AS q FROM v GROUP BY ProductCode, RTRIM(SeriesName), RTRIM(Bnumber)) b
    GROUP BY ProductCode
),
days AS (
    SELECT ProductCode, d, q,
           ROW_NUMBER() OVER (PARTITION BY ProductCode ORDER BY q DESC, d DESC) AS rn
    FROM (SELECT ProductCode, d, SUM(Quantity) AS q FROM v GROUP BY ProductCode, d) x
),
grn AS (
    SELECT ProductCode, MAX(LastgrnDate) AS last_received
    FROM ProductTrans WITH (NOLOCK)
    WHERE StoreName = @storename
    GROUP BY ProductCode
)
SELECT p.ProductCode, p.ProductName, p.TotalStock, p.SaleUnit, p.PurchasePrice, p.MRP,
       p.UnitDescription, p.SubLocation, p.ProductType,
       a.window_qty, a.bill_frequency, a.line_frequency, a.last_sale,
       b.max_bill_qty, dy.q AS max_day_qty, dy.d AS max_day_date, g.last_received
FROM Products p WITH (NOLOCK)
INNER JOIN agg a ON a.ProductCode = p.ProductCode
LEFT JOIN bills b ON b.ProductCode = p.ProductCode
LEFT JOIN days dy ON dy.ProductCode = p.ProductCode AND dy.rn = 1
LEFT JOIN grn g ON g.ProductCode = p.ProductCode
WHERE p.StoreName = @storename AND p.IsActive = 1
ORDER BY p.ProductName;
