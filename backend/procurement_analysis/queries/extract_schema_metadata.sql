/* =====================================================================
   OrderNMC — SCHEMA METADATA EXTRACTION (READ-ONLY)
   Purpose : Inventory tables/columns/keys/constraints/indexes/views/
             procedures/functions/triggers for the LPIE phase.
   Safety  : SELECT-only against INFORMATION_SCHEMA and sys.* catalog views.
             NO data or schema modifications. Run with a read-only login.
   Usage   : Run each section; paste results into database_inventory.md.
   ===================================================================== */
SET NOCOUNT ON;

/* 1. TABLES ----------------------------------------------------------- */
SELECT s.name AS [schema], t.name AS table_name,
       p.rows AS approx_rows
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id = t.schema_id
JOIN sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1)
ORDER BY t.name;

/* 2. COLUMNS ---------------------------------------------------------- */
SELECT TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, DATA_TYPE,
       CHARACTER_MAXIMUM_LENGTH AS max_len, NUMERIC_PRECISION AS prec,
       NUMERIC_SCALE AS scale, IS_NULLABLE, COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS
ORDER BY TABLE_NAME, ORDINAL_POSITION;

/* 3. PRIMARY KEYS ----------------------------------------------------- */
SELECT t.name AS table_name, i.name AS pk_name, c.name AS column_name, ic.key_ordinal
FROM sys.indexes i
JOIN sys.tables t ON t.object_id = i.object_id
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE i.is_primary_key = 1
ORDER BY t.name, ic.key_ordinal;

/* 4. FOREIGN KEYS ----------------------------------------------------- */
SELECT fk.name AS fk_name,
       ct.name AS child_table,  cc.name AS child_column,
       pt.name AS parent_table, pc.name AS parent_column,
       fk.delete_referential_action_desc AS on_delete,
       fk.update_referential_action_desc AS on_update
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
JOIN sys.tables  ct ON ct.object_id = fkc.parent_object_id
JOIN sys.columns cc ON cc.object_id = fkc.parent_object_id  AND cc.column_id = fkc.parent_column_id
JOIN sys.tables  pt ON pt.object_id = fkc.referenced_object_id
JOIN sys.columns pc ON pc.object_id = fkc.referenced_object_id AND pc.column_id = fkc.referenced_column_id
ORDER BY ct.name, fk.name;

/* 5. CHECK / UNIQUE / DEFAULT CONSTRAINTS ----------------------------- */
SELECT t.name AS table_name, con.name AS constraint_name, con.type_desc, dc.definition AS check_or_default
FROM sys.objects con
JOIN sys.tables t ON t.object_id = con.parent_object_id
LEFT JOIN sys.check_constraints  cc ON cc.object_id = con.object_id
LEFT JOIN sys.default_constraints dc ON dc.object_id = con.object_id
WHERE con.type IN ('C','D','UQ','PK','F')
ORDER BY t.name, con.type_desc;

/* 6. INDEXES ---------------------------------------------------------- */
SELECT t.name AS table_name, i.name AS index_name, i.type_desc,
       i.is_unique, ic.key_ordinal, c.name AS column_name
FROM sys.indexes i
JOIN sys.tables t ON t.object_id = i.object_id
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE i.is_primary_key = 0 AND i.type > 0
ORDER BY t.name, i.name, ic.key_ordinal;

/* 7. VIEWS ------------------------------------------------------------ */
SELECT TABLE_NAME AS view_name FROM INFORMATION_SCHEMA.VIEWS ORDER BY TABLE_NAME;
-- Definition text:
-- SELECT name, OBJECT_DEFINITION(object_id) AS definition FROM sys.views ORDER BY name;

/* 8. STORED PROCEDURES ------------------------------------------------ */
SELECT name AS procedure_name, create_date, modify_date FROM sys.procedures ORDER BY name;
-- Definition text (per proc):
-- SELECT OBJECT_DEFINITION(OBJECT_ID('<proc_name>'));

/* 9. FUNCTIONS -------------------------------------------------------- */
SELECT name AS function_name, type_desc, create_date, modify_date
FROM sys.objects WHERE type IN ('FN','IF','TF') ORDER BY name;

/* 10. TRIGGERS -------------------------------------------------------- */
SELECT tr.name AS trigger_name, t.name AS table_name,
       tr.is_disabled,
       OBJECTPROPERTY(tr.object_id,'ExecIsInsertTrigger') AS on_insert,
       OBJECTPROPERTY(tr.object_id,'ExecIsUpdateTrigger') AS on_update,
       OBJECTPROPERTY(tr.object_id,'ExecIsDeleteTrigger') AS on_delete
FROM sys.triggers tr
LEFT JOIN sys.tables t ON t.object_id = tr.parent_id
ORDER BY t.name, tr.name;

/* 11. OBJECT NAME SEARCH (procurement keywords) ----------------------- */
SELECT type_desc, name FROM sys.objects
WHERE name LIKE '%order%' OR name LIKE '%cycle%' OR name LIKE '%refresh%'
   OR name LIKE '%procure%' OR name LIKE '%supplier%' OR name LIKE '%demand%'
   OR name LIKE '%wanted%'  OR name LIKE '%pending%'  OR name LIKE '%grn%'
ORDER BY type_desc, name;
