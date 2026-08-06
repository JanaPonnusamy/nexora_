/* Procurement — per-store local supplier code mapping.
   Target database: NEXORA_PLATFORM (SQL Server).

   Mirrors dbo.Stores.Ho_code from the legacy OrderNMC database, but as a
   table instead of a single column so a store can carry a DIFFERENT local
   code for each internal source it distributes from (today just NMW/HO, but
   not limited to one). Example rows (from the legacy Ho_code column):

     store_code=NMS, source_store_code=NMW, local_supplier_code=94
     store_code=NMC, source_store_code=NMW, local_supplier_code=ST_2
     store_code=NMG, source_store_code=NMW, local_supplier_code=99
     store_code=NMA, source_store_code=NMW, local_supplier_code=94

   Read by distribution_service before writing procurement.supplier_stock so
   HO's rows land under the code that store's own systems actually know it
   by, not the literal source store code. Unmapped stores fall back to the
   source store code unchanged (same behaviour as before this table existed).
   Idempotent.
*/

IF OBJECT_ID('procurement.store_supplier_map', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.store_supplier_map
    (
        store_supplier_map_id UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id             UNIQUEIDENTIFIER NOT NULL,
        store_id              UNIQUEIDENTIFIER NOT NULL,
        source_store_code     VARCHAR(50)      NOT NULL,   /* e.g. NMW */
        local_supplier_code   VARCHAR(100)     NOT NULL,   /* e.g. 94, ST_2, 99 */
        created_at            DATETIME         NOT NULL DEFAULT GETDATE(),
        updated_at            DATETIME         NOT NULL DEFAULT GETDATE(),
        PRIMARY KEY (store_supplier_map_id),
        CONSTRAINT UQ_store_supplier_map UNIQUE (tenant_id, store_id, source_store_code)
    );
END
GO
