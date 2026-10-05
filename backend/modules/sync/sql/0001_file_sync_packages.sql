/* Sync -- FILE_TRANSFER package tracking (idempotency + audit ledger).
   Target database: NEXORA_PLATFORM (SQL Server 2014-compatible).

   One row per package a store's Store Agent produced for the FILE_TRANSFER
   transport (SFTP / email / file-drop instead of live DIRECT_HTTP). This is
   the idempotency guard objective 14 requires: package_id is the store's own
   execution_id (a GUID minted once when the package is built), so replaying
   the same physical .zip twice -- a retried email, a re-picked-up SFTP file,
   an operator re-dropping a file -- is a PRIMARY KEY violation, not a second
   import. checksum is stored too so a corrupted-but-same-id retransmission
   is caught before it ever reaches dbo.sync_execution / dbo.sync_chunk_execution.

   Deliberately NOT a new sync engine: once a package is validated + staged,
   every chunk inside it is imported through the exact same
   runtime_repository.upload_chunk() MERGE logic DIRECT_HTTP chunks already
   use, against the same dbo.sync_execution / dbo.sync_chunk_execution /
   dbo.sync_execution_details tables. This table only tracks the package
   envelope itself.

   Idempotent: safe to re-run.
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'sync')
    EXEC('CREATE SCHEMA sync');
GO

IF OBJECT_ID('sync.file_sync_packages', 'U') IS NULL
BEGIN
    CREATE TABLE sync.file_sync_packages
    (
        package_id          UNIQUEIDENTIFIER NOT NULL,
        execution_id         UNIQUEIDENTIFIER NOT NULL,
        tenant_id             UNIQUEIDENTIFIER NULL,
        store_id              UNIQUEIDENTIFIER NULL,

        source_filename       NVARCHAR(260)    NOT NULL,
        checksum              VARCHAR(64)      NOT NULL,   -- sha256 hex of the .zip
        transport_mode        VARCHAR(20)      NULL,       -- FILE_DROP / SFTP / EMAIL

        status                VARCHAR(20)      NOT NULL DEFAULT 'RECEIVED',
            -- RECEIVED -> VALIDATED -> STAGED -> IMPORTED
            --          -> REJECTED (validation failure, terminal)
            --          -> FAILED   (import failure, retryable)

        schema_version        INT              NULL,
        agent_version          VARCHAR(40)      NULL,
        total_rows             INT              NULL,
        total_chunks           INT              NULL,
        total_tables           INT              NULL,
        tables_imported        INT              NULL DEFAULT 0,
        tables_failed          INT              NULL DEFAULT 0,

        received_at            DATETIME         NOT NULL DEFAULT GETDATE(),
        import_started_at      DATETIME         NULL,
        import_completed_at    DATETIME         NULL,
        acknowledged_at        DATETIME         NULL,

        error_message          NVARCHAR(MAX)    NULL,
        manifest_json           NVARCHAR(MAX)    NULL,   -- full manifest, for audit/replay

        PRIMARY KEY (package_id)
    );

    -- One physical checksum should never import twice even under a
    -- different package_id (e.g. a store rebuilding an identical retry
    -- package after a crash before it persisted the id it used).
    CREATE UNIQUE INDEX UX_file_sync_packages_checksum
        ON sync.file_sync_packages (checksum);

    CREATE INDEX IX_file_sync_packages_store_status
        ON sync.file_sync_packages (store_id, status);
END
GO
