-- 001_sync_runtime_engine_part1.sql
SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO

CREATE TABLE dbo.sync_execution
(
    execution_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id UNIQUEIDENTIFIER NOT NULL,
    store_id UNIQUEIDENTIFIER NOT NULL,
    execution_type VARCHAR(50) NOT NULL,
    execution_status VARCHAR(50) NOT NULL,
    started_at DATETIME NOT NULL,
    completed_at DATETIME NULL,
    created_by UNIQUEIDENTIFIER NULL
);
GO

CREATE TABLE dbo.sync_chunk_execution
(
    chunk_execution_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    execution_id BIGINT NOT NULL,
    table_name VARCHAR(200) NOT NULL,
    chunk_no INT NOT NULL,
    status VARCHAR(50) NOT NULL,
    started_at DATETIME NULL,
    completed_at DATETIME NULL
);
GO

CREATE TABLE dbo.sync_execution_audit
(
    audit_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    execution_id BIGINT NOT NULL,
    audit_time DATETIME NOT NULL DEFAULT(GETDATE()),
    action_name VARCHAR(100) NOT NULL,
    action_details NVARCHAR(MAX) NULL
);
GO
