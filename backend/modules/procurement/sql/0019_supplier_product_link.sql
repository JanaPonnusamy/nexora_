/* Procurement — Product Intelligence 2.0: inline supplier-product assignment.
   Target database: NEXORA_PLATFORM (SQL Server).

   Mode 2 (Supplier Offer Intelligence) lists a supplier's live stock against the
   network. A supplier line the importer could not resolve to a store ProductCode
   is shown with an Assign action, and the buyer maps it WITHOUT leaving the
   screen. This table is where that decision is remembered.

   It does NOT duplicate the mapping engine:
     * supplier line -> the WAREHOUSE's ProductCode lives here (the same identity
       sync.SupplierProductMatch carries, which the platform does not write to —
       it is store-owned and sync-replicated).
     * warehouse ProductCode -> every OTHER store's ProductCode stays in
       dbo.product_mapping, written through the existing manual-remap path
       (status APPROVED, match_method MANUAL).

   Re-importing the supplier's file re-resolves through this table, so a manual
   assignment survives the next import. Idempotent.
*/

USE NEXORA_PLATFORM;
GO

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

IF OBJECT_ID('procurement.supplier_product_link', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.supplier_product_link
    (
        link_id               UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id             UNIQUEIDENTIFIER NOT NULL,
        store_id              UNIQUEIDENTIFIER NOT NULL,   /* the warehouse */
        supplier_code         VARCHAR(100)     NOT NULL,
        supplier_product_code VARCHAR(100)     NOT NULL,
        supplier_product_name VARCHAR(300)     NULL,

        product_code          VARCHAR(100)     NOT NULL,   /* store ProductCode */
        product_name          VARCHAR(400)     NULL,

        created_at            DATETIME         NOT NULL DEFAULT GETDATE(),
        created_by            UNIQUEIDENTIFIER NULL,
        updated_at            DATETIME         NULL,
        updated_by            UNIQUEIDENTIFIER NULL,
        is_deleted            BIT              NOT NULL DEFAULT 0,
        PRIMARY KEY (link_id)
    );

    CREATE UNIQUE INDEX UX_supplier_product_link
        ON procurement.supplier_product_link
           (tenant_id, store_id, supplier_code, supplier_product_code)
        WHERE is_deleted = 0;
END
GO
