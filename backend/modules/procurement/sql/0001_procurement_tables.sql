/* Procurement — Phase 2 (Platform Alignment): Cycle table.
   Target database: NEXORA_PLATFORM (SQL Server).

   procurement.procurement_cycles — the Business Cycle HEADER only.

   Phase 2 changes (approved):
     - Store only business BOUNDARY information; runtime parameters live on the
       Refresh. Removed: rolling_days, generated_product_count,
       live_refresh_count, last_refresh_id.
     - Kept active_refresh_id (pointer to the CURRENT Refresh).
     - Added GRN / Sale Bill boundary numbers (start_* / end_*).

   Platform conventions applied (source of truth = installer/sql/
   001_platform_foundation.sql):
     - PK format <entity>_id, UNIQUEIDENTIFIER, unnamed inline constraint.
     - VARCHAR (not NVARCHAR); DATETIME (not DATETIME2).
     - Audit: created_at/created_by/updated_at/updated_by, user refs are
       UNIQUEIDENTIFIER.
     - Soft delete: is_deleted / deleted_at / deleted_by (ratified platform
       standard, uniform across every procurement table).
     - No named PK_/FK_/CK_/DF_/UQ_ constraints.

   Idempotent: safe to run more than once.
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'procurement')
    EXEC('CREATE SCHEMA procurement');
GO

IF OBJECT_ID('procurement.procurement_cycles', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.procurement_cycles
    (
        cycle_id        UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id       UNIQUEIDENTIFIER NOT NULL,
        name            VARCHAR(200)     NOT NULL,
        description     VARCHAR(1000)    NULL,
        status          VARCHAR(50)      NOT NULL DEFAULT 'DRAFT',
        start_date      DATE             NULL,
        end_date        DATE             NULL,

        /* legacy order_cycles parity (evidence: nx_sp_RefreshOrderCycle) */
        store_id            UNIQUEIDENTIFIER NULL,
        cycle_no            INT              NULL,
        offline_mode        BIT              NOT NULL DEFAULT 0,
        active_refresh_id   UNIQUEIDENTIFIER NULL,   /* current Refresh pointer */
        closed_at           DATETIME         NULL,

        /* business boundary information (PR-BR-023 Store Completion) */
        start_grn_number        VARCHAR(50)  NULL,
        start_sale_bill_number  VARCHAR(50)  NULL,
        end_grn_number          VARCHAR(50)  NULL,
        end_sale_bill_number    VARCHAR(50)  NULL,

        /* audit */
        created_at      DATETIME         NOT NULL DEFAULT GETDATE(),
        created_by      UNIQUEIDENTIFIER NULL,
        updated_at      DATETIME         NULL,
        updated_by      UNIQUEIDENTIFIER NULL,

        /* soft delete */
        is_deleted      BIT              NOT NULL DEFAULT 0,
        deleted_at      DATETIME         NULL,
        deleted_by      UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (cycle_id)
    );

    CREATE INDEX IX_procurement_cycles_tenant
        ON procurement.procurement_cycles (tenant_id, is_deleted)
        INCLUDE (status);
END
GO
