/* Procurement — Supplier Reply (Export Monitor overhaul).
   Target database: NEXORA_PLATFORM (SQL Server).

   A supplier can send back the exported Excel with a per-line Status
   (Available / Partial / Not Available) + Available Qty BEFORE the physical
   goods sync into sync.PurchaseTrans — a pre-shipment confirmation, not a
   real GRN receipt. Deliberately separate columns from received_qty/grn_no/
   assignment_status (which reconciliation_service.py drives from actual
   synced receipts) so this signal never corrupts that state machine.

   procurement.supplier_product_exclusions: when a cycle closes with a
   partial/not-available reply still unresolved, that (supplier, product)
   pair is recorded here so Auto Assign / Rank Assign stop offering that
   supplier for that product on the NEXT cycle (owner-directed: "next order
   this product not assign to this supplier").

   Idempotent.
*/

IF COL_LENGTH('procurement.procurement_order_item_assignments', 'supplier_reply_status') IS NULL
    ALTER TABLE procurement.procurement_order_item_assignments
        ADD supplier_reply_status VARCHAR(20) NULL;  -- available | partial | not_available
GO

IF COL_LENGTH('procurement.procurement_order_item_assignments', 'supplier_reply_qty') IS NULL
    ALTER TABLE procurement.procurement_order_item_assignments
        ADD supplier_reply_qty DECIMAL(18,3) NULL;
GO

IF COL_LENGTH('procurement.procurement_order_item_assignments', 'supplier_reply_at') IS NULL
    ALTER TABLE procurement.procurement_order_item_assignments
        ADD supplier_reply_at DATETIME NULL;
GO

IF COL_LENGTH('procurement.procurement_order_item_assignments', 'supplier_reply_by') IS NULL
    ALTER TABLE procurement.procurement_order_item_assignments
        ADD supplier_reply_by UNIQUEIDENTIFIER NULL;
GO

IF OBJECT_ID('procurement.supplier_product_exclusions', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.supplier_product_exclusions
    (
        exclusion_id    UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id       UNIQUEIDENTIFIER NOT NULL,
        store_id        UNIQUEIDENTIFIER NULL,
        supplier_code   VARCHAR(100)     NOT NULL,
        product_code    VARCHAR(100)     NOT NULL,
        reason          VARCHAR(20)      NOT NULL,  -- partial | not_available
        cycle_id        UNIQUEIDENTIFIER NULL,
        created_at      DATETIME         NOT NULL DEFAULT GETDATE(),

        PRIMARY KEY (exclusion_id)
    );

    CREATE UNIQUE INDEX UX_supplier_product_exclusions
        ON procurement.supplier_product_exclusions (tenant_id, store_id, supplier_code, product_code);
END
GO
