/*  NMV integration — rollback.
    Run:  sqlcmd -S "DESKTOP-2\SQLEXPRESSORDER" -E -b -v DB=OrderNMC FORCE=0 -i 001_nmv_integration_rollback.sql
    Step 1 (always): drops the trigger and un-manages the store => VB behaves exactly as before.
    Step 2 (only if no un-acknowledged edits remain, or FORCE=1): drops the nmv_* tables.
    Existing VB tables/data are never touched. Orders already written to OrderManagement stay.
*/
:on error exit
SET NOCOUNT ON;
USE [$(DB)];
GO
IF OBJECT_ID('dbo.trg_nmv_OrderManagement_track','TR') IS NOT NULL
    DROP TRIGGER dbo.trg_nmv_OrderManagement_track;
IF OBJECT_ID('dbo.nmv_integration_store','U') IS NOT NULL
    UPDATE dbo.nmv_integration_store SET IsManaged = 0;   -- VB guards switch off immediately
PRINT 'Trigger dropped; integration guards disabled.';
GO
DECLARE @pending int = 0;
IF OBJECT_ID('dbo.nmv_change_queue','U') IS NOT NULL
    SELECT @pending = COUNT(*) FROM dbo.nmv_change_queue WHERE sync_state <> 'ACKED';
IF @pending > 0 AND '$(FORCE)' <> '1'
BEGIN
    RAISERROR('%d change(s) not yet acknowledged by HO. Tables kept. Export them or re-run with FORCE=1.', 16, 1, @pending);
    RETURN;
END;
IF OBJECT_ID('dbo.nmv_sync_audit','U')        IS NOT NULL DROP TABLE dbo.nmv_sync_audit;
IF OBJECT_ID('dbo.nmv_sync_state','U')        IS NOT NULL DROP TABLE dbo.nmv_sync_state;
IF OBJECT_ID('dbo.nmv_order_inbox','U')       IS NOT NULL DROP TABLE dbo.nmv_order_inbox;
IF OBJECT_ID('dbo.nmv_change_queue','U')      IS NOT NULL DROP TABLE dbo.nmv_change_queue;
IF OBJECT_ID('dbo.nmv_integration_store','U') IS NOT NULL DROP TABLE dbo.nmv_integration_store;
PRINT 'nmv_* tables dropped.';
GO
