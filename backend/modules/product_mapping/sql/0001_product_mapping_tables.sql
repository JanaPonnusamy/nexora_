/* Product Mapping Engine — core tables.
   Target database: NEXORA_PLATFORM (SQL Server).

   Cross-store / cross-supplier product matching. Deterministic rules first
   (supplier map -> exact name -> normalized name -> structured attributes),
   fuzzy last, human review below high confidence. HARD RULE: ProductCode is
   NOT a global identifier across stores and must never auto-match on its own
   (NMA 214 = GENPRAZ DSR TAB, NMC 214 = ROSCILLIN 250 INJ).

   Placement: dbo (platform) schema, alongside tenants/stores — approved scope.

   Platform conventions (source of truth = installer/sql/001_platform_foundation.sql):
     - PK <entity>_id, UNIQUEIDENTIFIER, unnamed inline constraint.
     - VARCHAR (not NVARCHAR); DATETIME (not DATETIME2).
     - tenant_id on every row; audit created_at/created_by/updated_at/updated_by
       (user refs UNIQUEIDENTIFIER); soft delete is_deleted/deleted_at/deleted_by.

   Idempotent: safe to run more than once.
*/

USE NEXORA_PLATFORM;
GO

/* Filtered/unique indexes below require these SET options ON. */
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

/* ---------------------------------------------------------------------------
   product_mapping — one row per (source product -> target store) decision.
   status: AUTO (auto-accepted, high confidence) | PENDING (needs review) |
           APPROVED (human confirmed) | REJECTED. Grouped by run_id.
--------------------------------------------------------------------------- */
IF OBJECT_ID('dbo.product_mapping', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_mapping
    (
        mapping_id              UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id               UNIQUEIDENTIFIER NOT NULL,
        run_id                  UNIQUEIDENTIFIER NOT NULL,

        /* source product (the thing we are mapping FROM) */
        source_store_id         UNIQUEIDENTIFIER NOT NULL,
        source_product_code     VARCHAR(50)      NOT NULL,
        source_product_name     VARCHAR(400)     NOT NULL,
        source_normalized_name  VARCHAR(400)     NULL,

        /* chosen target product (NULL while PENDING with no pick) */
        target_store_id         UNIQUEIDENTIFIER NOT NULL,
        target_product_code     VARCHAR(50)      NULL,
        target_product_name     VARCHAR(400)     NULL,

        /* decision metadata */
        match_method            VARCHAR(20)      NULL,   /* SUPPLIER/EXACT/NORMALIZED/STRUCTURED/FUZZY/MANUAL */
        match_phase             INT              NULL,   /* 1..7 */
        confidence              DECIMAL(5,2)     NOT NULL DEFAULT 0,
        status                  VARCHAR(20)      NOT NULL DEFAULT 'PENDING',

        /* parsed source attributes (structured medicine parser) */
        brand                   VARCHAR(200)     NULL,
        strength                VARCHAR(50)      NULL,
        unit                    VARCHAR(20)      NULL,
        dosage_form             VARCHAR(30)      NULL,
        pack_size               VARCHAR(30)      NULL,
        mrp                     DECIMAL(18,2)    NULL,

        /* audit */
        created_at              DATETIME         NOT NULL DEFAULT GETDATE(),
        created_by              UNIQUEIDENTIFIER NULL,
        updated_at              DATETIME         NULL,
        updated_by              UNIQUEIDENTIFIER NULL,

        /* soft delete */
        is_deleted              BIT              NOT NULL DEFAULT 0,
        deleted_at              DATETIME         NULL,
        deleted_by              UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (mapping_id)
    );

    /* one live mapping per source product -> target store */
    CREATE UNIQUE INDEX UX_product_mapping_source_target
        ON dbo.product_mapping (tenant_id, source_store_id, source_product_code, target_store_id)
        WHERE is_deleted = 0;

    CREATE INDEX IX_product_mapping_tenant_status
        ON dbo.product_mapping (tenant_id, is_deleted, status);

    CREATE INDEX IX_product_mapping_run
        ON dbo.product_mapping (run_id);
END
GO

/* ---------------------------------------------------------------------------
   product_mapping_candidate — ranked possible targets per mapping (for review).
--------------------------------------------------------------------------- */
IF OBJECT_ID('dbo.product_mapping_candidate', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_mapping_candidate
    (
        candidate_id            UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        mapping_id              UNIQUEIDENTIFIER NOT NULL,
        tenant_id               UNIQUEIDENTIFIER NOT NULL,

        target_product_code     VARCHAR(50)      NOT NULL,
        target_product_name     VARCHAR(400)     NOT NULL,
        target_normalized_name  VARCHAR(400)     NULL,

        /* per-signal + total score (0..100) */
        name_score              DECIMAL(5,2)     NOT NULL DEFAULT 0,
        brand_score             DECIMAL(5,2)     NOT NULL DEFAULT 0,
        strength_score          DECIMAL(5,2)     NOT NULL DEFAULT 0,
        form_score              DECIMAL(5,2)     NOT NULL DEFAULT 0,
        mrp_score               DECIMAL(5,2)     NOT NULL DEFAULT 0,
        total_score             DECIMAL(5,2)     NOT NULL DEFAULT 0,

        /* candidate attributes for the review screen */
        brand                   VARCHAR(200)     NULL,
        strength                VARCHAR(50)      NULL,
        dosage_form             VARCHAR(30)      NULL,
        mrp                     DECIMAL(18,2)    NULL,
        reason                  VARCHAR(500)     NULL,

        created_at              DATETIME         NOT NULL DEFAULT GETDATE(),

        PRIMARY KEY (candidate_id)
    );

    CREATE INDEX IX_product_mapping_candidate_mapping
        ON dbo.product_mapping_candidate (mapping_id, total_score DESC);
END
GO

/* ---------------------------------------------------------------------------
   product_mapping_audit — immutable history of every state change.
--------------------------------------------------------------------------- */
IF OBJECT_ID('dbo.product_mapping_audit', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_mapping_audit
    (
        audit_id        UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id       UNIQUEIDENTIFIER NOT NULL,
        mapping_id      UNIQUEIDENTIFIER NULL,
        run_id          UNIQUEIDENTIFIER NULL,
        action          VARCHAR(20)      NOT NULL,   /* RUN/AUTO_MATCH/APPROVE/REJECT/REMAP */
        old_status      VARCHAR(20)      NULL,
        new_status      VARCHAR(20)      NULL,
        actor_user_id   UNIQUEIDENTIFIER NULL,
        detail          VARCHAR(1000)    NULL,
        created_at      DATETIME         NOT NULL DEFAULT GETDATE(),

        PRIMARY KEY (audit_id)
    );

    CREATE INDEX IX_product_mapping_audit_mapping
        ON dbo.product_mapping_audit (mapping_id, created_at);
    CREATE INDEX IX_product_mapping_audit_tenant
        ON dbo.product_mapping_audit (tenant_id, created_at);
END
GO

/* ---------------------------------------------------------------------------
   product_normalization_dictionary — configurable dosage-form / unit / noise
   words. tenant_id NULL = global default. kind: DOSAGE_FORM | UNIT | NOISE.
--------------------------------------------------------------------------- */
IF OBJECT_ID('dbo.product_normalization_dictionary', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_normalization_dictionary
    (
        entry_id        UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id       UNIQUEIDENTIFIER NULL,       /* NULL = global */
        term            VARCHAR(50)      NOT NULL,    /* uppercase token as seen in names */
        canonical       VARCHAR(50)      NULL,        /* normalized attribute value */
        kind            VARCHAR(20)      NOT NULL DEFAULT 'DOSAGE_FORM',
        is_active       BIT              NOT NULL DEFAULT 1,

        created_at      DATETIME         NOT NULL DEFAULT GETDATE(),
        created_by      UNIQUEIDENTIFIER NULL,
        updated_at      DATETIME         NULL,
        updated_by      UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (entry_id)
    );

    CREATE UNIQUE INDEX UX_product_norm_dict_term
        ON dbo.product_normalization_dictionary (tenant_id, term)
        WHERE tenant_id IS NOT NULL;
    /* global terms are unique on term alone */
    CREATE UNIQUE INDEX UX_product_norm_dict_term_global
        ON dbo.product_normalization_dictionary (term)
        WHERE tenant_id IS NULL;
END
GO

/* ---------------------------------------------------------------------------
   Seed the global normalization dictionary (dosage forms + units).
   Only dosage-form / unit / noise words are stripped during normalization —
   numeric strengths (650, 500, 0.5, 12.5) are ALWAYS kept.
--------------------------------------------------------------------------- */
;WITH seed(term, canonical, kind) AS (
    SELECT * FROM (VALUES
        ('TABLET','TAB','DOSAGE_FORM'), ('TABLETS','TAB','DOSAGE_FORM'),
        ('TABS','TAB','DOSAGE_FORM'),   ('TAB','TAB','DOSAGE_FORM'),
        ('CAPSULE','CAP','DOSAGE_FORM'),('CAPSULES','CAP','DOSAGE_FORM'),
        ('CAPS','CAP','DOSAGE_FORM'),   ('CAP','CAP','DOSAGE_FORM'),
        ('SYRUP','SYP','DOSAGE_FORM'),  ('SYP','SYP','DOSAGE_FORM'),
        ('SUSPENSION','SUSP','DOSAGE_FORM'), ('SUSP','SUSP','DOSAGE_FORM'),
        ('SUS','SUSP','DOSAGE_FORM'),
        ('INJECTION','INJ','DOSAGE_FORM'), ('INJ','INJ','DOSAGE_FORM'),
        ('DROPS','DROP','DOSAGE_FORM'), ('DROP','DROP','DOSAGE_FORM'),
        ('CREAM','CREAM','DOSAGE_FORM'),
        ('OINTMENT','OINT','DOSAGE_FORM'), ('OINT','OINT','DOSAGE_FORM'),
        ('GEL','GEL','DOSAGE_FORM'),
        ('LOTION','LOTION','DOSAGE_FORM'),
        ('SPRAY','SPRAY','DOSAGE_FORM'),
        ('SOAP','SOAP','DOSAGE_FORM'),
        ('POWDER','POWDER','DOSAGE_FORM'),
        ('SACHET','SACHET','DOSAGE_FORM'),
        ('SOLUTION','SOLN','DOSAGE_FORM'), ('SOLN','SOLN','DOSAGE_FORM'),
        ('MG','MG','UNIT'), ('MCG','MCG','UNIT'), ('GM','GM','UNIT'),
        ('ML','ML','UNIT'), ('IU','IU','UNIT'), ('MG/ML','MG/ML','UNIT')
    ) AS v(term, canonical, kind)
)
INSERT INTO dbo.product_normalization_dictionary (entry_id, tenant_id, term, canonical, kind, is_active)
SELECT NEWID(), NULL, s.term, s.canonical, s.kind, 1
FROM seed s
WHERE NOT EXISTS (
    SELECT 1 FROM dbo.product_normalization_dictionary d
    WHERE d.tenant_id IS NULL AND d.term = s.term
);
GO

/* ---------------------------------------------------------------------------
   Register the Product Mapping module for RBAC (idempotent).
--------------------------------------------------------------------------- */
IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE module_code = 'PRODUCT_MAPPING')
BEGIN
    INSERT INTO dbo.modules (module_id, module_code, module_name, description, is_active)
    VALUES (NEWID(), 'PRODUCT_MAPPING', 'Product Mapping', 'Cross-store product mapping engine', 1);
END
GO
