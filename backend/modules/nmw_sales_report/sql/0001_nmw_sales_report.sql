-- NMW Sales Report (Bill-wise) schema.
-- The module self-heals this same DDL at runtime (repository._ensure_schema);
-- this file documents it and can be applied ahead of time.

-- 1. Approval state owned by Nexora (super admin approves the dispatch).
IF OBJECT_ID('dbo.nmw_sales_dispatch_approval') IS NULL
CREATE TABLE dbo.nmw_sales_dispatch_approval (
    tenant_id       uniqueidentifier NOT NULL,
    source_store_id uniqueidentifier NOT NULL,   -- NMW warehouse store
    bill_date       datetime         NOT NULL,
    bnumber         varchar(50)      NOT NULL,
    status          varchar(20)      NOT NULL CONSTRAINT DF_nmw_dispatch_status DEFAULT('approved'),
    approved_by     varchar(200)     NULL,
    approved_at     datetime         NULL,
    remarks         varchar(500)     NULL,
    CONSTRAINT PK_nmw_sales_dispatch_approval
        PRIMARY KEY (tenant_id, source_store_id, bill_date, bnumber)
);
GO

-- 2. Per-store NMW customer code (sales-side mirror of Ho_code). The report
--    joins SaleInformation.CustomerCode = stores.ho_cust_code to route bills.
IF COL_LENGTH('dbo.stores', 'ho_cust_code') IS NULL
    ALTER TABLE dbo.stores ADD ho_cust_code varchar(50) NULL;
GO

-- 3. Despatch signal: ensure IssuedDate is synced on sync.SaleInformation.
IF COL_LENGTH('sync.SaleInformation', 'IssuedDate') IS NULL
    ALTER TABLE sync.SaleInformation ADD IssuedDate datetime NULL;
GO

IF EXISTS (SELECT 1 FROM sync.sync_column_mapping WHERE table_name = 'SaleInformation')
   AND NOT EXISTS (
       SELECT 1 FROM sync.sync_column_mapping
       WHERE table_name = 'SaleInformation' AND column_name = 'IssuedDate')
INSERT INTO sync.sync_column_mapping
    (mapping_id, sync_table_id, table_name, column_name, data_type,
     is_selected, is_pk, is_hash, is_watermark, column_order, created_at)
SELECT NEWID(), MAX(sync_table_id), 'SaleInformation', 'IssuedDate', 'datetime',
       1, 0, 0, 0, ISNULL(MAX(column_order), 0) + 1, GETDATE()
FROM sync.sync_column_mapping
WHERE table_name = 'SaleInformation';
GO
