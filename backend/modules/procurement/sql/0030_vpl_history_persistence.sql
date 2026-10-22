/* Procurement — Step 4: durable VPL History persistence.
   Target database: NEXORA_PLATFORM (SQL Server).
   NOT APPLIED. Written for review only — do not run against NEXORA_PLATFORM
   or OrderNMC without explicit authorization.

   Implements the "Revised data contract" accepted in principle
   (PHASE_2_VPL_HISTORY.md, 2026-10-20) and the "Concurrency design"
   section of the same document. This migration SUPERSEDES
   0027_vpl_history.sql's batch/line tables — 0027 keyed a history line by
   (history_id, product_code) and stored supplier_code/rare_confirmed
   directly on the line; the accepted revision explicitly states
   "0027 is not the parent" and separates supplier assignments into their
   own child table keyed by source_assignment_id, with no supplier columns
   on the line itself, and keeps rare-mover confirmation OUT of history
   (that is 0028_rare_mover_confirmation.sql's job, on the live order item,
   decided independently this session as D3c).

   Do NOT apply 0027's batch/line CREATE TABLE statements alongside this
   file — run this instead of that portion of 0027. 0027's row_version
   ADD COLUMN on procurement_order_items is still correct and is reused
   here (IF COL_LENGTH guard makes re-running it harmless either way).

   Source ids (source_order_item_id, source_assignment_id, source_refresh_id)
   are immutable historical copies, not live foreign keys — a later edit or
   delete of the live row never touches history and never fails on a
   dangling reference.
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'procurement')
    EXEC('CREATE SCHEMA procurement');
GO

/* ---------------------------------------------------------------------------
   History batch — one per refresh that replaced a working set.
--------------------------------------------------------------------------- */
IF OBJECT_ID('procurement.vpl_history_batch', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.vpl_history_batch
    (
        history_id          UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id           UNIQUEIDENTIFIER NOT NULL,
        store_id            UNIQUEIDENTIFIER NOT NULL,
        cycle_id            UNIQUEIDENTIFIER NOT NULL,
        source_refresh_id   UNIQUEIDENTIFIER NOT NULL,
        successor_refresh_id UNIQUEIDENTIFIER NOT NULL,
        rule_snapshot_id    UNIQUEIDENTIFIER NULL,
        line_count          INT              NOT NULL,
        created_at          DATETIME         NOT NULL DEFAULT GETDATE(),
        created_by          UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (history_id),
        FOREIGN KEY (cycle_id) REFERENCES procurement.procurement_cycles (cycle_id),
        FOREIGN KEY (source_refresh_id) REFERENCES procurement.procurement_refreshes (refresh_id)
    );

    CREATE UNIQUE INDEX UX_vpl_history_batch_refresh_pair
        ON procurement.vpl_history_batch (tenant_id, source_refresh_id, successor_refresh_id);

    CREATE INDEX IX_vpl_history_batch_store
        ON procurement.vpl_history_batch (tenant_id, store_id, created_at);
END
GO

/* ---------------------------------------------------------------------------
   History line — one per working-order-item snapshot inside a batch.
   Key is (history_id, source_order_item_id), NOT product_code — product_code
   is nullable and not unique; product_id/product_code are copied attributes.
   No supplier columns here (see Assignment child below) and no
   rare_confirmed column (D3c keeps confirmation on the live order item,
   not in history — a confirmation is scoped to the current cycle only and
   has no meaning once archived).
--------------------------------------------------------------------------- */
IF OBJECT_ID('procurement.vpl_history_line', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.vpl_history_line
    (
        history_id            UNIQUEIDENTIFIER NOT NULL,
        source_order_item_id  UNIQUEIDENTIFIER NOT NULL,
        tenant_id              UNIQUEIDENTIFIER NOT NULL,
        store_id               UNIQUEIDENTIFIER NULL,
        cycle_id               UNIQUEIDENTIFIER NOT NULL,
        source_refresh_id      UNIQUEIDENTIFIER NOT NULL,

        product_id             UNIQUEIDENTIFIER NULL,
        product_code           VARCHAR(100)     NULL,

        suggested_qty          DECIMAL(18,3)    NULL,
        final_qty              DECIMAL(18,3)    NULL,
        manual_override        BIT              NOT NULL DEFAULT 0,
        item_status            VARCHAR(20)      NULL,
        skip_reason            VARCHAR(300)     NULL,
        reviewed_by            UNIQUEIDENTIFIER NULL,
        reviewed_at            DATETIME         NULL,
        reason_code            VARCHAR(50)      NULL,
        row_version            INT              NOT NULL,
        carried_forward        BIT              NOT NULL DEFAULT 0,

        copied_at              DATETIME         NOT NULL DEFAULT GETDATE(),

        PRIMARY KEY (history_id, source_order_item_id),
        FOREIGN KEY (history_id) REFERENCES procurement.vpl_history_batch (history_id)
    );

    CREATE INDEX IX_vpl_history_line_product
        ON procurement.vpl_history_line (tenant_id, product_id);
END
GO

/* ---------------------------------------------------------------------------
   Assignment child — zero or more supplier assignments per history line,
   copied at snapshot time. Foreign key is to the HISTORY line
   (history_id, source_order_item_id), not to the live assignment — the
   live assignment may later be changed, removed, or exported without any
   effect on this copy.
--------------------------------------------------------------------------- */
IF OBJECT_ID('procurement.vpl_history_assignment', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.vpl_history_assignment
    (
        history_id            UNIQUEIDENTIFIER NOT NULL,
        source_assignment_id  UNIQUEIDENTIFIER NOT NULL,
        source_order_item_id  UNIQUEIDENTIFIER NOT NULL,

        tenant_id              UNIQUEIDENTIFIER NOT NULL,
        store_id               UNIQUEIDENTIFIER NULL,
        cycle_id               UNIQUEIDENTIFIER NOT NULL,
        source_refresh_id      UNIQUEIDENTIFIER NOT NULL,

        supplier_code          VARCHAR(100)     NULL,
        assigned_qty           DECIMAL(18,3)    NULL,
        assignment_status      VARCHAR(20)      NULL,

        copied_at              DATETIME         NOT NULL DEFAULT GETDATE(),

        PRIMARY KEY (history_id, source_assignment_id),
        FOREIGN KEY (history_id, source_order_item_id)
            REFERENCES procurement.vpl_history_line (history_id, source_order_item_id)
    );
END
GO

/* ---------------------------------------------------------------------------
   Removed (manual-review) line — one live row per
   (tenant_id, store_id, cycle_id, product_id) representing a manually
   touched working item whose product did not appear in the latest
   generation. Cleared (restored_at set, not hard-deleted) when the product
   reappears. The filtered unique index enforces "at most one ACTIVE removed
   row" while allowing the full episode history to remain queryable.
--------------------------------------------------------------------------- */
IF OBJECT_ID('procurement.vpl_removed_line', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.vpl_removed_line
    (
        removed_id              UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id                UNIQUEIDENTIFIER NOT NULL,
        store_id                 UNIQUEIDENTIFIER NOT NULL,
        cycle_id                 UNIQUEIDENTIFIER NOT NULL,
        product_id                UNIQUEIDENTIFIER NOT NULL,
        product_code              VARCHAR(100)     NULL,

        originating_refresh_id    UNIQUEIDENTIFIER NOT NULL,
        originating_cycle_id      UNIQUEIDENTIFIER NOT NULL,
        removed_during_refresh_id UNIQUEIDENTIFIER NOT NULL,

        /* preserved manual state — same shape as procurement_order_items'
           PM-editable fields, so reappearance can write these straight
           onto the new order item */
        final_qty                 DECIMAL(18,3)    NULL,
        manual_override           BIT              NOT NULL DEFAULT 0,
        override_reason           VARCHAR(300)     NULL,
        supplier_code              VARCHAR(100)     NULL,
        assigned_qty               DECIMAL(18,3)    NULL,

        removed_at                 DATETIME         NOT NULL DEFAULT GETDATE(),
        removed_by                 UNIQUEIDENTIFIER NULL,
        restored_at                DATETIME         NULL,
        restored_by                UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (removed_id),
        FOREIGN KEY (originating_refresh_id) REFERENCES procurement.procurement_refreshes (refresh_id)
    );

    CREATE UNIQUE INDEX UX_vpl_removed_line_active
        ON procurement.vpl_removed_line (tenant_id, store_id, cycle_id, product_id)
        WHERE restored_at IS NULL;

    CREATE INDEX IX_vpl_removed_line_cycle
        ON procurement.vpl_removed_line (tenant_id, cycle_id, removed_at);
END
GO

/* ---------------------------------------------------------------------------
   Concurrency (PHASE_2_VPL_HISTORY.md "Concurrency design" section):
   one row_version per table, compare-and-swap on every mutating write.
   procurement_order_items.row_version is reused from 0027 (same column,
   same default) — re-running this guard is harmless if 0027 was already
   applied in isolation; only one of the two will ever actually add it.
--------------------------------------------------------------------------- */
IF COL_LENGTH('procurement.procurement_order_items', 'row_version') IS NULL
    ALTER TABLE procurement.procurement_order_items
        ADD row_version INT NOT NULL DEFAULT 1;
GO

IF COL_LENGTH('procurement.procurement_order_item_assignments', 'row_version') IS NULL
    ALTER TABLE procurement.procurement_order_item_assignments
        ADD row_version INT NOT NULL DEFAULT 1;
GO

IF COL_LENGTH('procurement.procurement_refreshes', 'row_version') IS NULL
    ALTER TABLE procurement.procurement_refreshes
        ADD row_version INT NOT NULL DEFAULT 1;
GO
