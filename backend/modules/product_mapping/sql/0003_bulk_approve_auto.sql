/* One-off bulk approve of status='AUTO' product_mapping rows for a tenant,
   preserving the exact safety rules repository.set_status()/
   _upsert_supplier_product_match() enforce per-row (see those docstrings):
   skip a row when the source store has no procurement.store_supplier_map
   link to the target store, and skip a row when sync.SupplierProductMatch
   already holds a DIFFERENT ProductCode for that (store, SupplierCode,
   SupplierProductCode) -- never silently overwritten.

   Parameter: @tenant_id. Run against NEXORA_PLATFORM.
*/
DECLARE @tenant_id UNIQUEIDENTIFIER = 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D';
DECLARE @now DATETIME = GETDATE();

;WITH resolvable AS (
    SELECT
        pm.mapping_id, pm.source_store_id, pm.target_store_id,
        pm.source_product_code, pm.target_product_code, pm.target_product_name,
        ssm.local_supplier_code AS supplier_code
    FROM dbo.product_mapping pm
    JOIN dbo.stores target_st ON target_st.store_id = pm.target_store_id
    JOIN procurement.store_supplier_map ssm
      ON ssm.tenant_id = pm.tenant_id
     AND ssm.store_id = pm.source_store_id
     AND ssm.source_store_code = target_st.store_code
    WHERE pm.tenant_id = @tenant_id
      AND pm.is_deleted = 0
      AND pm.status = 'AUTO'
      AND pm.target_product_code IS NOT NULL
),
blocked AS (
    SELECT r.mapping_id
    FROM resolvable r
    JOIN sync.SupplierProductMatch spm
      ON spm.store_id = r.source_store_id
     AND spm.SupplierCode = r.supplier_code
     AND spm.SupplierProductCode = r.source_product_code
    WHERE spm.ProductCode IS NOT NULL
      AND TRY_CAST(spm.ProductCode AS INT) <> TRY_CAST(r.source_product_code AS INT)
),
approvable AS (
    SELECT r.* FROM resolvable r
    WHERE NOT EXISTS (SELECT 1 FROM blocked b WHERE b.mapping_id = r.mapping_id)
      AND TRY_CAST(r.source_product_code AS INT) IS NOT NULL
)
MERGE sync.SupplierProductMatch AS tgt
USING (
    SELECT source_store_id AS store_id, supplier_code AS SupplierCode,
           source_product_code AS SupplierProductCode,
           target_product_code AS ProductCode, target_product_name AS ProductName
    FROM approvable
) AS src
ON tgt.store_id = src.store_id AND tgt.SupplierCode = src.SupplierCode
   AND tgt.SupplierProductCode = src.SupplierProductCode
WHEN NOT MATCHED THEN
    INSERT (store_id, SupplierCode, SupplierProductCode, ProductCode, ProductName)
    VALUES (src.store_id, src.SupplierCode, src.SupplierProductCode, src.ProductCode, src.ProductName);
GO

UPDATE pm SET status = 'APPROVED', updated_at = GETDATE()
FROM dbo.product_mapping pm
JOIN dbo.stores target_st ON target_st.store_id = pm.target_store_id
JOIN procurement.store_supplier_map ssm
  ON ssm.tenant_id = pm.tenant_id
 AND ssm.store_id = pm.source_store_id
 AND ssm.source_store_code = target_st.store_code
WHERE pm.tenant_id = 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D'
  AND pm.is_deleted = 0
  AND pm.status = 'AUTO'
  AND pm.target_product_code IS NOT NULL
  AND TRY_CAST(pm.source_product_code AS INT) IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM sync.SupplierProductMatch spm
      WHERE spm.store_id = pm.source_store_id
        AND spm.SupplierCode = ssm.local_supplier_code
        AND spm.SupplierProductCode = pm.source_product_code
        AND spm.ProductCode IS NOT NULL
        AND TRY_CAST(spm.ProductCode AS INT) <> TRY_CAST(pm.source_product_code AS INT)
  );
GO

SELECT status, COUNT(*) FROM dbo.product_mapping
WHERE tenant_id = 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D' AND is_deleted = 0
GROUP BY status;
GO
