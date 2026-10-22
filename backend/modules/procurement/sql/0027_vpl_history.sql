/* VPL history for a refresh that replaces the working set.
   Target database: NEXORA_PLATFORM (SQL Server).
   NOT APPLIED. No isolated test database was used. Do not run this on
   NEXORA_PLATFORM or OrderNMC.

   What already exists and is reused, not copied:
     procurement.procurement_cycles          <- OrderNMC order_cycles
     procurement.procurement_refreshes       <- order_cycle_refreshes
     procurement.procurement_virtual_products <- order_virtual_items
     procurement.procurement_order_items     <- order_items (the working lines)
     procurement.procurement_order_item_assignments

   OrderHeaderDetails stays on OrderNMC, keyed by StoreName + OrderId.
   This script does not alter it. OrderManagement is not altered.

   Why a new table: decision_repository.clear_products deletes
   procurement_virtual_products for one refresh_id before regenerating.
   Older refresh_ids are a history of successful refreshes, but that delete
   destroys the current refresh's previous lines with no copy. These tables
   are the copy. The latest-10 limit is a query limit, not a delete.

   row_version on procurement_order_items is the optimistic-concurrency
   column the live table does not have. Existing rows receive 1. Current
   workspace updates do not read it until a later cutover.

   rule_snapshot_id has no foreign key. Migration 0026 is unapplied, so a
   key to rule_effective_snapshot would fail. The id is stored as given.
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'procurement')
    EXEC('CREATE SCHEMA procurement');
GO

IF OBJECT_ID('procurement.vpl_history_batch', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.vpl_history_batch
    (
        history_id          UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id           UNIQUEIDENTIFIER NOT NULL,
        store_id            UNIQUEIDENTIFIER NOT NULL,
        cycle_id            UNIQUEIDENTIFIER NOT NULL,
        source_refresh_id   UNIQUEIDENTIFIER NOT NULL,
        rule_snapshot_id    UNIQUEIDENTIFIER NULL,
        line_count          INT              NOT NULL,
        created_at          DATETIME         NOT NULL DEFAULT GETDATE(),
        created_by          UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (history_id)
    );

    CREATE INDEX IX_vpl_history_batch_store
        ON procurement.vpl_history_batch (tenant_id, store_id, created_at);
END
GO

IF OBJECT_ID('procurement.vpl_history_line', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.vpl_history_line
    (
        history_id          UNIQUEIDENTIFIER NOT NULL,
        product_code        VARCHAR(100)     NOT NULL,
        product_id          UNIQUEIDENTIFIER NULL,
        suggested_qty       DECIMAL(18,3)    NULL,
        final_qty           DECIMAL(18,3)    NULL,
        manual_override     BIT              NOT NULL DEFAULT 0,
        supplier_code       VARCHAR(100)     NULL,
        assigned_qty        DECIMAL(18,3)    NULL,
        rare_confirmed      BIT              NOT NULL DEFAULT 0,
        reviewed_at         DATETIME         NULL,
        reason_code         VARCHAR(50)      NULL,
        row_version         INT              NOT NULL,
        carried_forward     BIT              NOT NULL DEFAULT 0,

        PRIMARY KEY (history_id, product_code),
        FOREIGN KEY (history_id) REFERENCES procurement.vpl_history_batch (history_id)
    );
END
GO

IF COL_LENGTH('procurement.procurement_order_items', 'row_version') IS NULL
    ALTER TABLE procurement.procurement_order_items
        ADD row_version INT NOT NULL DEFAULT 1;
GO
