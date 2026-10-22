/* Procurement Rules Registry.
   Target database: NEXORA_PLATFORM (SQL Server).
   NOT APPLIED. No isolated test database was verified when this file was added.

   Why these objects exist:
   procurement_refreshes already stores rolling_days, min_days, and max_days.
   Those three numbers cannot store the effective rule set, its source
   (default vs store override), or the audit trail. supplier_export_settings
   is store+supplier only and is not a rule catalog. OrderHeaderDetails is
   not modified.

   rule_snapshot_id on procurement_refreshes is a nullable pointer for a
   FUTURE refresh. Existing rows stay NULL. There is no foreign key, so a
   snapshot can be retained after a refresh soft-delete and the rollback
   below can refuse when any refresh already points at a snapshot.

   The Python catalog in rules_catalog.py is the seed. This script does not
   invent rule values. Runtime resolution still uses the process registry
   until a later approved cutover reads these tables. decision_rules is
   untouched.

   Idempotent.
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'procurement')
    EXEC('CREATE SCHEMA procurement');
GO

IF OBJECT_ID('procurement.rule_definition', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.rule_definition
    (
        rule_id             VARCHAR(64)      NOT NULL,
        name                VARCHAR(200)     NOT NULL,
        category            VARCHAR(40)      NOT NULL,
        rule_group          VARCHAR(40)      NOT NULL,
        description         VARCHAR(1000)    NOT NULL,
        source_evidence     VARCHAR(1000)    NOT NULL,
        current_behavior    VARCHAR(1000)    NOT NULL,
        target_behavior     VARCHAR(1000)    NOT NULL,
        status              VARCHAR(40)      NOT NULL,
        value_type          VARCHAR(20)      NOT NULL,
        default_value       VARCHAR(500)     NULL,
        validation_text     VARCHAR(500)     NOT NULL,
        override_policy     VARCHAR(20)      NOT NULL,
        min_value           DECIMAL(18,4)    NULL,
        max_value           DECIMAL(18,4)    NULL,
        allowed_values      VARCHAR(500)     NULL,
        created_at          DATETIME         NOT NULL DEFAULT GETDATE(),
        updated_at          DATETIME         NULL,

        PRIMARY KEY (rule_id)
    );
END
GO

IF OBJECT_ID('procurement.rule_default_revision', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.rule_default_revision
    (
        revision_id         UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        rule_id             VARCHAR(64)      NOT NULL,
        value_text          VARCHAR(500)     NULL,
        reason              VARCHAR(500)     NOT NULL,
        row_version         INT              NOT NULL,
        is_current          BIT              NOT NULL DEFAULT 1,
        created_at          DATETIME         NOT NULL DEFAULT GETDATE(),
        created_by          UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (revision_id),
        FOREIGN KEY (rule_id) REFERENCES procurement.rule_definition (rule_id)
    );

    CREATE INDEX IX_rule_default_revision_current
        ON procurement.rule_default_revision (rule_id, is_current);
END
GO

IF OBJECT_ID('procurement.rule_store_override', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.rule_store_override
    (
        tenant_id           UNIQUEIDENTIFIER NOT NULL,
        store_id            UNIQUEIDENTIFIER NOT NULL,
        rule_id             VARCHAR(64)      NOT NULL,
        value_text          VARCHAR(500)     NOT NULL,
        row_version         INT              NOT NULL,
        reason              VARCHAR(500)     NOT NULL,
        updated_at          DATETIME         NOT NULL DEFAULT GETDATE(),
        updated_by          UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (tenant_id, store_id, rule_id),
        FOREIGN KEY (rule_id) REFERENCES procurement.rule_definition (rule_id)
    );
END
GO

IF OBJECT_ID('procurement.rule_change_audit', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.rule_change_audit
    (
        audit_id            UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id           UNIQUEIDENTIFIER NULL,
        store_id            UNIQUEIDENTIFIER NULL,
        rule_id             VARCHAR(64)      NOT NULL,
        change_kind         VARCHAR(20)      NOT NULL,
        previous_value      VARCHAR(500)     NULL,
        new_value           VARCHAR(500)     NULL,
        reason              VARCHAR(500)     NOT NULL,
        row_version         INT              NOT NULL,
        editor_id           UNIQUEIDENTIFIER NULL,
        changed_at          DATETIME         NOT NULL DEFAULT GETDATE(),

        PRIMARY KEY (audit_id),
        FOREIGN KEY (rule_id) REFERENCES procurement.rule_definition (rule_id)
    );

    CREATE INDEX IX_rule_change_audit_store
        ON procurement.rule_change_audit (tenant_id, store_id, rule_id, changed_at);
END
GO

IF OBJECT_ID('procurement.rule_effective_snapshot', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.rule_effective_snapshot
    (
        snapshot_id         UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id           UNIQUEIDENTIFIER NOT NULL,
        store_id            UNIQUEIDENTIFIER NOT NULL,
        content_hash        VARCHAR(64)      NOT NULL,
        applies_to          VARCHAR(40)      NOT NULL DEFAULT 'future_refresh_only',
        created_at          DATETIME         NOT NULL DEFAULT GETDATE(),
        created_by          UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (snapshot_id)
    );

    CREATE INDEX IX_rule_effective_snapshot_store
        ON procurement.rule_effective_snapshot (tenant_id, store_id, created_at);
END
GO

IF OBJECT_ID('procurement.rule_effective_snapshot_item', 'U') IS NULL
BEGIN
    CREATE TABLE procurement.rule_effective_snapshot_item
    (
        snapshot_id         UNIQUEIDENTIFIER NOT NULL,
        rule_id             VARCHAR(64)      NOT NULL,
        effective_value     VARCHAR(500)     NULL,
        value_source        VARCHAR(20)      NOT NULL,
        rule_status         VARCHAR(40)      NOT NULL,

        PRIMARY KEY (snapshot_id, rule_id),
        FOREIGN KEY (snapshot_id) REFERENCES procurement.rule_effective_snapshot (snapshot_id),
        FOREIGN KEY (rule_id) REFERENCES procurement.rule_definition (rule_id)
    );
END
GO

IF COL_LENGTH('procurement.procurement_refreshes', 'rule_snapshot_id') IS NULL
    ALTER TABLE procurement.procurement_refreshes
        ADD rule_snapshot_id UNIQUEIDENTIFIER NULL;
GO
