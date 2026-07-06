/* Procurement — Phase 2 (Platform Alignment): Order Item Assignments
   Target database: NEXORA_PLATFORM (SQL Server).

   procurement.procurement_order_item_assignments — a working order item's
   quantity allocated to a supplier, through to GRN reconciliation. An order
   item may receive more than one assignment.

   Export is NOT a separate entity: there is no Export Header / PO Header /
   Export Master. Export tracking lives here (export_batch_number allows
   multiple exports).

   Phase 2 changes (approved):
     - PK id -> assignment_id; FK -> order_items(order_item_id),
       refreshes(refresh_id), cycles(cycle_id).
     - Added export tracking: export_batch_number, export_split_number,
       export_uid, exported_at, exported_by.
     - Audit -> created_at/created_by/updated_at/updated_by (user refs GUID);
       soft delete -> is_deleted/deleted_at/deleted_by; VARCHAR + DATETIME;
       unnamed constraints.

   Idempotent.
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'procurement')
    EXEC('CREATE SCHEMA procurement');
GO

IF OBJECT_ID('procurement.procurement_order_item_assignments', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.procurement_order_item_assignments
    (
        assignment_id   UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id       UNIQUEIDENTIFIER NOT NULL,
        cycle_id        UNIQUEIDENTIFIER NOT NULL,
        refresh_id      UNIQUEIDENTIFIER NOT NULL,
        order_item_id   UNIQUEIDENTIFIER NOT NULL,
        store_id        UNIQUEIDENTIFIER NULL,

        /* legacy order_item_assignments parity */
        product_code      VARCHAR(100)   NULL,
        supplier_code     VARCHAR(100)   NOT NULL,
        assigned_qty      DECIMAL(18,3)  NULL,
        assignment_status VARCHAR(30)    NOT NULL DEFAULT 'draft',
                                        /* draft | exported | partial_received */
        remarks           VARCHAR(300)   NULL,

        /* export tracking (multiple exports via export_batch_number) */
        export_batch_number VARCHAR(50)      NULL,
        export_split_number INT              NULL,
        export_uid          VARCHAR(100)     NULL,
        exported_at         DATETIME         NULL,
        exported_by         UNIQUEIDENTIFIER NULL,

        /* GRN reconciliation (legacy ValidationResponse) */
        received_qty      DECIMAL(18,3)  NULL,
        grn_no            VARCHAR(100)   NULL,
        supplier_bill_no  VARCHAR(100)   NULL,

        /* audit */
        created_at      DATETIME         NOT NULL DEFAULT GETDATE(),
        created_by      UNIQUEIDENTIFIER NULL,
        updated_at      DATETIME         NULL,
        updated_by      UNIQUEIDENTIFIER NULL,

        /* soft delete */
        is_deleted      BIT              NOT NULL DEFAULT 0,
        deleted_at      DATETIME         NULL,
        deleted_by      UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (assignment_id),
        FOREIGN KEY (order_item_id)
            REFERENCES procurement.procurement_order_items (order_item_id),
        FOREIGN KEY (refresh_id)
            REFERENCES procurement.procurement_refreshes (refresh_id),
        FOREIGN KEY (cycle_id)
            REFERENCES procurement.procurement_cycles (cycle_id)
    );

    CREATE INDEX IX_procurement_assignments_tenant
        ON procurement.procurement_order_item_assignments (tenant_id, is_deleted)
        INCLUDE (refresh_id, cycle_id, assignment_status);

    CREATE INDEX IX_procurement_assignments_order_item
        ON procurement.procurement_order_item_assignments (order_item_id, is_deleted);

    CREATE INDEX IX_procurement_assignments_supplier
        ON procurement.procurement_order_item_assignments (tenant_id, supplier_code, is_deleted);

    CREATE INDEX IX_procurement_assignments_export_batch
        ON procurement.procurement_order_item_assignments (tenant_id, export_batch_number, is_deleted);
END
GO
