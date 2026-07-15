/* Procurement — Learned Product Category (Shelf Sorting "trainable agent").
   Target database: NEXORA_PLATFORM (SQL Server).

   The shelf-sort category for a product is normally derived from keyword rules
   / UnitDescription, but many products (e.g. a toothpaste whose name carries
   no form word) can't be. This table LEARNS the category for a product so it
   is remembered across cycles and stores:

     - source 'manual'      : a human confirmed it on the review screen — wins.
     - source 'llm'         : Claude auto-classified it (a suggestion until
                              confirmed).
     - source 'cross_store' : borrowed from another store's UnitDescription.

   Keyed by tenant + a NORMALISED product name (upper-cased, collapsed spaces)
   — NOT ProductCode, which is not consistent across stores (that is exactly
   why the Product Mapping module exists). So a category learned once applies
   to every store in the tenant that stocks the same product.

   Idempotent.
*/

IF OBJECT_ID('procurement.product_category', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.product_category
    (
        tenant_id     UNIQUEIDENTIFIER NOT NULL,
        product_key   NVARCHAR(300)    NOT NULL,  -- normalised product name
        category      VARCHAR(40)      NOT NULL,  -- e.g. 'Paste', 'Food', 'Tablet'
        source        VARCHAR(20)      NOT NULL DEFAULT 'manual',  -- manual | llm | cross_store
        confirmed     BIT              NOT NULL DEFAULT 0,         -- human-confirmed
        sample_name   NVARCHAR(300)    NULL,      -- an original (un-normalised) name, for display
        updated_by    UNIQUEIDENTIFIER NULL,
        updated_at    DATETIME         NOT NULL DEFAULT GETDATE(),

        PRIMARY KEY (tenant_id, product_key)
    );
END
GO
