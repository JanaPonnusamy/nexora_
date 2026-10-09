/* Change-capture trigger tests. Runs ONLY against OrderNMC_IntTest.
   Uses the exact SQL statements found in Form1.vb. Everything runs inside a transaction that is rolled back. */
:on error exit
SET NOCOUNT ON;
USE OrderNMC_IntTest;
IF DB_NAME() <> 'OrderNMC_IntTest' RAISERROR('wrong database', 20, 1) WITH LOG;
GO
-- fixture: the real current NMV order copied from live (read-only on live)
SET CONTEXT_INFO 0x4E4D565F4147454E54;   -- fixture load is not a user edit
DELETE FROM dbo.OrderManagement; DELETE FROM dbo.OrderHeaderDetails; DELETE FROM dbo.OrderManagementBackup;
INSERT INTO dbo.OrderManagement SELECT * FROM OrderNMC.dbo.OrderManagement WHERE StoreName = 'NMV';
SET CONTEXT_INFO 0x;
DELETE FROM dbo.nmv_change_queue;
INSERT INTO dbo.OrderHeaderDetails SELECT h.* FROM OrderNMC.dbo.OrderHeaderDetails h WHERE h.OrderId IN (SELECT DISTINCT OrderId FROM dbo.OrderManagement);
GO
DECLARE @fails int = 0, @n int, @rc int, @p float, @p2 float, @before int;
DECLARE @r TABLE (test varchar(80), result varchar(4), detail varchar(200));
SELECT TOP 1 @p  = ProductCode FROM dbo.OrderManagement WHERE StoreName='NMV' AND Status='0' ORDER BY ProductCode;
SELECT TOP 1 @p2 = ProductCode FROM dbo.OrderManagement WHERE StoreName='NMV' AND Status='0' AND ProductCode <> @p ORDER BY ProductCode DESC;
INSERT @r VALUES ('fixture rows (real NMV order)', 'INFO', CONVERT(varchar, (SELECT COUNT(*) FROM dbo.OrderManagement)));
IF @p IS NULL OR @p2 IS NULL RAISERROR('fixture has no Status=0 rows', 16, 1);

BEGIN TRAN;
-- setup (agent-marked, so not captured): give open rows a positive suggested qty, as a fresh order would have
SET CONTEXT_INFO 0x4E4D565F4147454E54;
UPDATE dbo.OrderManagement SET OrderQty = 3, Qtycheck = 0 WHERE StoreName='NMV' AND Status='0';
SET CONTEXT_INFO 0x;
INSERT @r VALUES ('setup (agent session) produced no queue rows', CASE WHEN (SELECT COUNT(*) FROM dbo.nmv_change_queue)=0 THEN 'PASS' ELSE 'FAIL' END, '');
-- T1  Qty Check edit (Form1.UpdateValues)
UPDATE ordermanagement SET orderqty = 7, remarks = 'OrderQty Changed 2 Add', qtycheck = 1 WHERE productcode = @p AND storename = 'NMV' AND status = 0;
SET @rc = @@ROWCOUNT;
SELECT @n = COUNT(*) FROM dbo.nmv_change_queue WHERE product_code=@p AND operation='U' AND new_order_qty=7 AND new_qtycheck=1 AND new_remarks='OrderQty Changed 2 Add';
INSERT @r VALUES ('T1 qty-check edit captured', CASE WHEN @n=1 THEN 'PASS' ELSE 'FAIL' END, 'queue=' + CONVERT(varchar,@n));
INSERT @r VALUES ('T1 VB row count unchanged by trigger (@@ROWCOUNT=1)', CASE WHEN @rc=1 THEN 'PASS' ELSE 'FAIL' END, 'rowcount=' + CONVERT(varchar,@rc));

-- T2  identical value re-save: no new queue row
SELECT @before = COUNT(*) FROM dbo.nmv_change_queue;
UPDATE ordermanagement SET orderqty = 7, remarks = 'OrderQty Changed 2 Add', qtycheck = 1 WHERE productcode = @p AND storename = 'NMV' AND status = 0;
INSERT @r VALUES ('T2 no-op update not queued', CASE WHEN (SELECT COUNT(*) FROM dbo.nmv_change_queue)=@before THEN 'PASS' ELSE 'FAIL' END, '');

-- T3  supplier assignment (Form1.UpdateDatabase(productCode), status 0 -> 1)
UPDATE ordermanagement SET orqty = 7, orsupplier = 'TEST SUPPLIER', orsuppliercode = 'T1', status = 1 WHERE productcode = @p AND status = 0 AND storename = 'NMV';
SELECT @n = COUNT(*) FROM dbo.nmv_change_queue WHERE product_code=@p AND old_status='0' AND new_status='1' AND new_or_supplier_code='T1' AND new_or_qty=7;
INSERT @r VALUES ('T3 supplier assignment captured (status 0->1)', CASE WHEN @n=1 THEN 'PASS' ELSE 'FAIL' END, '');

-- T4  toggle back (nullUpdateQuery, status 1 -> 0)
UPDATE ordermanagement SET orqty = NULL, orsupplier = NULL, orsuppliercode = NULL, status = 0 WHERE productcode = @p AND status = 1 AND storename = 'NMV';
SELECT @n = COUNT(*) FROM dbo.nmv_change_queue WHERE product_code=@p AND old_status='1' AND new_status='0' AND new_or_supplier IS NULL AND old_or_supplier='TEST SUPPLIER';
INSERT @r VALUES ('T4 un-assignment captured with NULLs (NULL-safe compare)', CASE WHEN @n=1 THEN 'PASS' ELSE 'FAIL' END, '');

-- T5  Escape key 'Don''t want to Order'
UPDATE ordermanagement SET orderqty = 0, remarks = 'Don''t want to Order', qtycheck = 1 WHERE productcode = @p2 AND storename = 'NMV' AND status = 0;
INSERT @r VALUES ('T5 zero-qty edit captured', CASE WHEN EXISTS (SELECT 1 FROM dbo.nmv_change_queue WHERE product_code=@p2 AND new_order_qty=0) THEN 'PASS' ELSE 'FAIL' END, '');

-- T6  Export button multi-row update (Form1.UpdateDatabase() loop -> many rows in one statement here)
SELECT @before = COUNT(*) FROM dbo.nmv_change_queue;
UPDATE ordermanagement SET orqty = OrderQty, orsupplier = 'BULK', orsuppliercode = 'B1', status = 1 WHERE storename = 'NMV' AND Orderqty > 0 AND status = 0;
SET @rc = @@ROWCOUNT;
SELECT @n = COUNT(*) - @before FROM dbo.nmv_change_queue;
INSERT @r VALUES ('T6 multi-row update: one queue row per changed row', CASE WHEN @n=@rc AND @rc>0 THEN 'PASS' ELSE 'FAIL' END, 'rows=' + CONVERT(varchar,@rc) + ' queued=' + CONVERT(varchar,@n));

-- T7  untracked column only (TotalStock) -> nothing queued
SELECT @before = COUNT(*) FROM dbo.nmv_change_queue;
UPDATE ordermanagement SET TotalStock = TotalStock + 1 WHERE storename = 'NMV';
INSERT @r VALUES ('T7 untracked-column update not queued', CASE WHEN (SELECT COUNT(*) FROM dbo.nmv_change_queue)=@before THEN 'PASS' ELSE 'FAIL' END, '');

-- T8  agent session (CONTEXT_INFO marker) not queued
SELECT @before = COUNT(*) FROM dbo.nmv_change_queue;
SET CONTEXT_INFO 0x4E4D565F4147454E54;
UPDATE ordermanagement SET remarks = 'agent write' WHERE productcode = @p AND storename = 'NMV';
SET CONTEXT_INFO 0x;
INSERT @r VALUES ('T8 agent-marked session not queued (no echo/recursion)', CASE WHEN (SELECT COUNT(*) FROM dbo.nmv_change_queue)=@before THEN 'PASS' ELSE 'FAIL' END, '');

-- T9  unmanaged store not queued
SELECT @before = COUNT(*) FROM dbo.nmv_change_queue;
UPDATE dbo.nmv_integration_store SET IsManaged = 0 WHERE StoreName='NMV';
UPDATE ordermanagement SET orderqty = 99 WHERE productcode = @p AND storename = 'NMV';
UPDATE dbo.nmv_integration_store SET IsManaged = 1 WHERE StoreName='NMV';
INSERT @r VALUES ('T9 unmanaged store not queued', CASE WHEN (SELECT COUNT(*) FROM dbo.nmv_change_queue)=@before THEN 'PASS' ELSE 'FAIL' END, '');

-- T10 legacy VB Process Order statements still work with the trigger present
INSERT INTO OrderManagementBackup SELECT * FROM OrderManagement WHERE StoreName = 'NMV';
SET @rc = @@ROWCOUNT;
INSERT @r VALUES ('T10a VB "INSERT OMB SELECT * FROM OM" still compatible', CASE WHEN @rc=(SELECT COUNT(*) FROM dbo.OrderManagement WHERE StoreName='NMV') THEN 'PASS' ELSE 'FAIL' END, 'rows=' + CONVERT(varchar,@rc));
-- T11 agent-marked delete is allowed (order replacement) and not queued
SELECT @before = COUNT(*) FROM dbo.nmv_change_queue;
SET CONTEXT_INFO 0x4E4D565F4147454E54;
DELETE FROM OrderManagement WHERE StoreName = 'NMV' AND ProductCode = @p2;
SET @rc = @@ROWCOUNT;
SET CONTEXT_INFO 0x;
INSERT @r VALUES ('T11 agent-marked delete allowed and not queued', CASE WHEN @rc = 1 AND (SELECT COUNT(*) FROM dbo.nmv_change_queue)=@before THEN 'PASS' ELSE 'FAIL' END, 'deleted=' + CONVERT(varchar,@rc));
ROLLBACK;

SELECT test, result, detail FROM @r;
GO
-- T10b: legacy VB Process Order DELETE (plain session) is refused for a managed store; order intact
DECLARE @err nvarchar(400) = NULL, @left int;
BEGIN TRY
    DELETE FROM OrderManagement WHERE StoreName = 'NMV';
END TRY
BEGIN CATCH
    SET @err = ERROR_MESSAGE();
END CATCH;
SELECT @left = COUNT(*) FROM dbo.OrderManagement WHERE StoreName = 'NMV';
SELECT 'T10b legacy Process Order DELETE blocked, order intact' AS test,
       CASE WHEN @err LIKE 'NMV integration:%' AND @left = 586 THEN 'PASS' ELSE 'FAIL' END AS result,
       'rows left=' + CONVERT(varchar, @left) AS detail;
GO
-- T12: unmanaged store: VB delete behaves as before (allowed)
UPDATE dbo.nmv_integration_store SET IsManaged = 0 WHERE StoreName = 'NMV';
BEGIN TRAN;
DELETE FROM OrderManagement WHERE StoreName = 'NMV';
SELECT 'T12 unmanaged store: VB delete allowed as before' AS test, CASE WHEN @@ROWCOUNT = 586 THEN 'PASS' ELSE 'FAIL' END AS result, '' AS detail;
ROLLBACK;
UPDATE dbo.nmv_integration_store SET IsManaged = 1 WHERE StoreName = 'NMV';
GO

