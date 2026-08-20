/* Procurement — Internal Supplier Stock Distribution.
   Target database: NEXORA_PLATFORM (SQL Server).

   Distributes ONE store's own stock (the group's internal "HO" supplier,
   e.g. NMW) out to every other store as a supplier_stock feed — the reverse
   direction of the external Supplier Live Stock importer
   (procurement.supplier_stock, see 0009/0010). Writes land in the SAME
   procurement.supplier_stock table with supplier_code = the source store's
   code and source = 'internal_distribution', so the existing read endpoint
   (GET .../supplier-stock) needs no changes to see HO stock as a supplier.

   distribution_config  — which stores receive the feed + where to notify.
   distribution_run      — one row per "Generate" click (parent).
   distribution_run_item — one row per target store within a run (child; the
                            per-store log the UI grid renders).
   distribution_queue    — WhatsApp send queue, populated after a successful
                            run_item; no sender is wired yet (queued only).
   Idempotent.
*/

IF OBJECT_ID('procurement.distribution_config', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.distribution_config
    (
        distribution_config_id UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id              UNIQUEIDENTIFIER NOT NULL,
        store_id                UNIQUEIDENTIFIER NOT NULL,
        store_code               VARCHAR(50)      NOT NULL,
        whatsapp_group          VARCHAR(200)     NULL,
        phone_number             VARCHAR(30)      NULL,
        enabled                 BIT              NOT NULL DEFAULT 1,
        created_at              DATETIME         NOT NULL DEFAULT GETDATE(),
        updated_at              DATETIME         NOT NULL DEFAULT GETDATE(),
        PRIMARY KEY (distribution_config_id),
        CONSTRAINT UQ_distribution_config_store UNIQUE (tenant_id, store_id)
    );
END
GO

IF OBJECT_ID('procurement.distribution_run', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.distribution_run
    (
        run_id            UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id         UNIQUEIDENTIFIER NOT NULL,
        source_store_code VARCHAR(50)      NOT NULL,   /* e.g. NMW */
        provider          VARCHAR(20)      NOT NULL,   /* legacy | nexora */
        started_at        DATETIME         NOT NULL DEFAULT GETDATE(),
        finished_at       DATETIME         NULL,
        status            VARCHAR(20)      NOT NULL DEFAULT 'running',  /* running|completed|failed */
        stores_total       INT              NOT NULL DEFAULT 0,
        stores_succeeded   INT              NOT NULL DEFAULT 0,
        stores_failed      INT              NOT NULL DEFAULT 0,
        started_by         UNIQUEIDENTIFIER NULL,
        PRIMARY KEY (run_id)
    );
END
GO

IF OBJECT_ID('procurement.distribution_run_item', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.distribution_run_item
    (
        run_item_id     UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        run_id           UNIQUEIDENTIFIER NOT NULL,
        tenant_id        UNIQUEIDENTIFIER NOT NULL,
        store_id          UNIQUEIDENTIFIER NOT NULL,
        store_code         VARCHAR(50)      NOT NULL,
        started_at        DATETIME         NOT NULL DEFAULT GETDATE(),
        finished_at        DATETIME         NULL,
        duration_ms        INT              NULL,
        rows_exported      INT              NULL,
        rows_imported      INT              NULL,
        excel_path          VARCHAR(500)     NULL,
        supplier_updated   BIT              NOT NULL DEFAULT 0,
        whatsapp_status    VARCHAR(20)      NOT NULL DEFAULT 'not_queued', /* not_queued|queued|sent|failed */
        status            VARCHAR(20)      NOT NULL DEFAULT 'running',    /* running|success|failed */
        error_message      VARCHAR(1000)    NULL,
        PRIMARY KEY (run_item_id),
        CONSTRAINT FK_distribution_run_item_run FOREIGN KEY (run_id)
            REFERENCES procurement.distribution_run (run_id)
    );

    CREATE INDEX IX_distribution_run_item_run
        ON procurement.distribution_run_item (run_id);
END
GO

IF OBJECT_ID('procurement.distribution_queue', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.distribution_queue
    (
        queue_id       UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        run_item_id     UNIQUEIDENTIFIER NOT NULL,
        tenant_id       UNIQUEIDENTIFIER NOT NULL,
        store_id         UNIQUEIDENTIFIER NOT NULL,
        whatsapp_group  VARCHAR(200)     NULL,
        phone_number     VARCHAR(30)      NULL,
        excel_path        VARCHAR(500)     NULL,
        status          VARCHAR(20)      NOT NULL DEFAULT 'queued',  /* queued|sent|failed */
        queued_at        DATETIME         NOT NULL DEFAULT GETDATE(),
        sent_at           DATETIME         NULL,
        error_message    VARCHAR(1000)    NULL,
        PRIMARY KEY (queue_id),
        CONSTRAINT FK_distribution_queue_run_item FOREIGN KEY (run_item_id)
            REFERENCES procurement.distribution_run_item (run_item_id)
    );
END
GO
