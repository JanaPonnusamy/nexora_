/* Rollback for 0027_vpl_history.sql. NOT APPLIED.
   Refuses to drop history that already has batches.
   Does not drop OrderHeaderDetails, OrderManagement, cycles, refreshes,
   virtual products, order items, or assignments.
*/

IF OBJECT_ID('procurement.vpl_history_batch', 'U') IS NOT NULL
   AND EXISTS (SELECT 1 FROM procurement.vpl_history_batch)
BEGIN
    THROW 50027, 'Refusing rollback: VPL history batches already exist.', 1;
END
GO

IF OBJECT_ID('procurement.vpl_history_line', 'U') IS NOT NULL
    DROP TABLE procurement.vpl_history_line;
GO
IF OBJECT_ID('procurement.vpl_history_batch', 'U') IS NOT NULL
    DROP TABLE procurement.vpl_history_batch;
GO

IF COL_LENGTH('procurement.procurement_order_items', 'row_version') IS NOT NULL
   AND EXISTS (
        SELECT 1 FROM procurement.procurement_order_items WHERE row_version > 1
   )
BEGIN
    THROW 50027, 'Refusing rollback: a working line row_version has moved past 1.', 1;
END
GO

IF COL_LENGTH('procurement.procurement_order_items', 'row_version') IS NOT NULL
BEGIN
    DECLARE @row_version_default sysname;
    SELECT @row_version_default = dc.name
    FROM sys.default_constraints dc
    INNER JOIN sys.columns c
        ON c.object_id = dc.parent_object_id
       AND c.column_id = dc.parent_column_id
    WHERE dc.parent_object_id = OBJECT_ID('procurement.procurement_order_items')
      AND c.name = 'row_version';
    IF @row_version_default IS NOT NULL
        EXEC('ALTER TABLE procurement.procurement_order_items DROP CONSTRAINT [' + @row_version_default + ']');
    ALTER TABLE procurement.procurement_order_items DROP COLUMN row_version;
END
GO
