-- Pass Gen — maps a Nexora store (alphanumeric store_code, e.g. NMS) onto the
-- numeric store code the legacy passcode format needs (2 digits, e.g. 6).
-- The number is not derivable from dbo.stores, so it is held here and edited
-- from the Pass Gen page.

IF OBJECT_ID('dbo.pass_gen_store_code', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.pass_gen_store_code (
        store_id     UNIQUEIDENTIFIER NOT NULL
                     CONSTRAINT PK_pass_gen_store_code PRIMARY KEY,
        numeric_code INT NOT NULL,
        updated_at   DATETIME2 NOT NULL
                     CONSTRAINT DF_pass_gen_store_code_updated DEFAULT SYSUTCDATETIME(),
        CONSTRAINT FK_pass_gen_store_code_store
            FOREIGN KEY (store_id) REFERENCES dbo.stores (store_id)
    );
END;

-- Seed the four stores whose legacy numbers are known (from storeheader.json).
MERGE dbo.pass_gen_store_code AS target
USING (
    SELECT s.store_id, v.numeric_code
    FROM (VALUES ('NMS', 6), ('NMC', 7), ('NMG', 8), ('NMA', 9)) AS v (store_code, numeric_code)
    JOIN dbo.stores s ON s.store_code = v.store_code
) AS source
ON target.store_id = source.store_id
WHEN NOT MATCHED THEN
    INSERT (store_id, numeric_code) VALUES (source.store_id, source.numeric_code);
