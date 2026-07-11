/* Document Extraction Engine — migration 0002 (Chunk 14, Integration).

   Surfaced by wiring Product Resolution (Chunk 10) into the real pipeline:
   doc_import_item.product_code's FK to dbo.doc_product_mapping (0001) only
   holds for the NEW_MAPPING/EXISTING_MAPPING sources — a MASTER_PRODUCT
   resolution deliberately returns the platform's REAL sync.Products
   ProductCode (see product_resolution.py's module docstring), which was
   never meant to exist in doc_product_mapping and would violate that FK.

   Fix: drop the FK (product_code can now legitimately reference either
   table depending on source) and add product_code_source so callers
   (Review UI, Excel export, History) can tell which one a given row is —
   without it, "482" (a real store product) and "DOC000000482" would look
   identical downstream.
*/

USE NEXORA_PLATFORM;
GO

IF EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE parent_object_id = OBJECT_ID('dbo.doc_import_item')
      AND referenced_object_id = OBJECT_ID('dbo.doc_product_mapping')
)
BEGIN
    DECLARE @fk_name NVARCHAR(200) = (
        SELECT TOP 1 name FROM sys.foreign_keys
        WHERE parent_object_id = OBJECT_ID('dbo.doc_import_item')
          AND referenced_object_id = OBJECT_ID('dbo.doc_product_mapping')
    );
    EXEC('ALTER TABLE dbo.doc_import_item DROP CONSTRAINT ' + @fk_name);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.doc_import_item') AND name = 'product_code_source'
)
BEGIN
    ALTER TABLE dbo.doc_import_item
        ADD product_code_source NVARCHAR(20) NULL;  /* EXISTING_MAPPING / MASTER_PRODUCT / NEW_MAPPING */
END
GO
