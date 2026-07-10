/* Document Extraction Engine — core schema (Chunk 2, simplified).
   Target database: NEXORA_PLATFORM (SQL Server 2014 compatible).

   Scope: Upload -> OCR -> Extract -> User Review -> Store -> Export Excel.
   Nothing else. This is an invoice OCR extraction module, not a document
   management platform, workflow engine, template engine, OCR platform, or
   audit platform. No purchase posting, no ERP integration, no accounting,
   no inventory update — this schema has no write path into any procurement/
   sync table.

   Revision note: an earlier draft of this migration (18 tables: document
   type/processing job/page/file/header/ocr raw/ocr block/template/template
   header/template column/validation/review-session/audit as separate
   tables) was rejected as over-engineered for V1 and discarded before being
   applied anywhere. This is the replacement — 6 tables total, JSON columns
   used in place of the tables that added structure without a V1 requirement
   for it.

   Table prefix: doc_ (generic document engine naming, per instruction,
   even though V1 only ever populates it with invoices).

   Platform conventions reused (source of truth = installer/sql/
   001_platform_foundation.sql, confirmed against product_mapping and
   procurement migrations):
     - dbo schema, flat (no new SQL schema).
     - tenant_id UNIQUEIDENTIFIER NOT NULL on every table.
     - Unnamed inline PRIMARY KEY / FOREIGN KEY constraints.
     - Status columns are plain NVARCHAR with a DEFAULT and the valid
       vocabulary documented in a comment, no CHECK constraint.
     - Soft delete (is_deleted/deleted_at/deleted_by) on mutable entity
       tables only, never on append-only log tables.
     - Index naming IX_<table>_<cols>, unique UX_<table>_<cols>.
     - Idempotent: safe to run more than once.

   Platform conventions overridden per explicit instruction (unchanged from
   the discarded draft, still applies): PK is BIGINT IDENTITY(1,1), not
   UNIQUEIDENTIFIER (scale rationale: tens of millions of invoice lines);
   NVARCHAR instead of VARCHAR (OCR text may carry non-Latin glyphs);
   DATETIME2(3) instead of DATETIME.
*/

USE NEXORA_PLATFORM;
GO

SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO

/* =============================================================================
   1. doc_import — ONE ROW PER INVOICE. Everything about the invoice as a
      whole lives here: file locations, raw OCR payload, every header field
      (raw OCR value where it matters + final parsed value), supplier
      detection result, and validation outcome. This intentionally folds
      what would otherwise be separate page/file/header/supplier/validation
      tables into one row, because V1 has exactly one of each per invoice.

      status (pipeline stage): UPLOADED / OCR_RUNNING / EXTRACTED /
        REVIEW_PENDING / SAVED / EXPORTED / FAILED
      validation_status: PENDING / PASSED / WARNING / FAILED
      supplier_match_method: GST / DL / PHONE / NAME / MANUAL / UNKNOWN
============================================================================= */
IF OBJECT_ID('dbo.doc_import', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.doc_import
    (
        import_id             BIGINT IDENTITY(1,1) NOT NULL,
        import_guid           UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        tenant_id             UNIQUEIDENTIFIER NOT NULL,
        store_id              UNIQUEIDENTIFIER NULL,

        /* pipeline state — status is the coarse state machine (see Workflow
           doc); the is_*_completed flags below are a fast bit-level progress
           readout for the Processing Queue UI so it doesn't have to parse
           `status` strings to render a 7-step progress indicator. Both are
           kept in sync by the same code path that advances `status`. */
        status                NVARCHAR(30)     NOT NULL DEFAULT 'UPLOADED',
        failure_reason        NVARCHAR(500)    NULL,

        is_upload_completed    BIT NOT NULL DEFAULT 0,
        is_image_processed     BIT NOT NULL DEFAULT 0,
        is_ocr_completed       BIT NOT NULL DEFAULT 0,
        is_header_extracted    BIT NOT NULL DEFAULT 0,
        is_items_extracted     BIT NOT NULL DEFAULT 0,
        is_reviewed            BIT NOT NULL DEFAULT 0,
        is_exported            BIT NOT NULL DEFAULT 0,

        /* files + page order. original_file_path stays a single path (the
           first/primary page) for quick access; original_files_json is the
           authoritative structured page list — the "OriginalFiles" JSON
           contract (see Document_Extraction_JSON_Contracts.md). Every
           element carries page_no/original_file_name/storage_path/
           display_order/rotation/processing_status, satisfying the
           per-page metadata requirement without a doc_page table.
           processed_files_json is the "ProcessedFiles" contract, populated
           by image preprocessing (Chunk 5) — NULL until then. */
        source_type            NVARCHAR(20)     NOT NULL,   /* PDF/JPG/JPEG/PNG/TIFF/CAMERA */
        original_file_path     NVARCHAR(1000)   NOT NULL,
        original_file_checksum CHAR(64)         NULL,   /* SHA-256 of the uploaded bytes; fixed-length hex, CHAR not "varchar" */
        original_files_json    NVARCHAR(MAX)    NULL,
        processed_files_json   NVARCHAR(MAX)    NULL,
        preview_image_path     NVARCHAR(1000)   NULL,
        page_count              INT              NULL,

        /* raw OCR payload for the whole document (all pages). Contract:
           this column stores the NORMALIZED OCR model (OCRResult — see JSON
           Contracts doc), never the raw PaddleOCR response verbatim; the
           normalization step is mandatory (Design doc § OCR output
           contract), not optional cleanup. */
        ocr_json              NVARCHAR(MAX)    NULL,
        ocr_confidence        DECIMAL(5,2)     NULL,

        /* supplier detection (GST -> DL -> Phone -> Name priority chain) */
        ocr_supplier_name             NVARCHAR(200)    NULL,
        supplier_name                 NVARCHAR(200)    NULL,
        gst_number                    NVARCHAR(20)     NULL,
        dl_number                     NVARCHAR(50)     NULL,
        supplier_phone                NVARCHAR(20)     NULL,
        supplier_address              NVARCHAR(500)    NULL,
        matched_supplier_code         NVARCHAR(50)     NULL,
        supplier_match_method         NVARCHAR(20)     NULL,
        supplier_match_confidence     DECIMAL(5,2)     NULL,
        is_supplier_unknown           BIT              NOT NULL DEFAULT 0,

        /* header — raw OCR value kept for the two fields most prone to
           OCR/parse divergence, final parsed value for everything */
        ocr_invoice_number    NVARCHAR(50)     NULL,
        invoice_number         NVARCHAR(50)     NULL,
        ocr_invoice_date       NVARCHAR(20)     NULL,
        invoice_date           DATE             NULL,
        invoice_type           NVARCHAR(30)     NULL,
        order_number           NVARCHAR(50)     NULL,
        transport               NVARCHAR(100)    NULL,
        salesman                NVARCHAR(100)    NULL,
        credit_days              INT              NULL,

        gross_amount       DECIMAL(18,2)    NULL,
        discount_amount    DECIMAL(18,2)    NULL,
        scheme_discount    DECIMAL(18,2)    NULL,
        cash_discount      DECIMAL(18,2)    NULL,
        taxable_amount     DECIMAL(18,2)    NULL,
        cgst_amount        DECIMAL(18,2)    NULL,
        sgst_amount        DECIMAL(18,2)    NULL,
        igst_amount        DECIMAL(18,2)    NULL,
        cess_amount        DECIMAL(18,2)    NULL,
        round_off          DECIMAL(10,2)    NULL,
        net_amount         DECIMAL(18,2)    NULL,
        item_count         INT              NULL,
        total_quantity     DECIMAL(18,3)    NULL,

        irn_number                NVARCHAR(100)    NULL,   /* e-invoice, optional */
        ack_number                 NVARCHAR(50)     NULL,
        ack_date                    DATE             NULL,
        gst_slab_breakup_json        NVARCHAR(MAX)    NULL,   /* variable slab rows, see Database doc */

        /* validation — findings stored as JSON instead of a child table.
           Contract: Validation (see JSON Contracts doc). */
        validation_status    NVARCHAR(20)     NOT NULL DEFAULT 'PENDING',
        validation_json      NVARCHAR(MAX)    NULL,

        /* denormalized copy of the most recent doc_export_history row for
           this import, so the Review/History pages can show "last exported"
           without a join; doc_export_history remains the authoritative full
           list. Contract: ExportInfo (see JSON Contracts doc). */
        latest_export_json    NVARCHAR(MAX)    NULL,

        is_duplicate              BIT              NOT NULL DEFAULT 0,
        duplicate_of_import_id    BIGINT           NULL,

        uploaded_by    UNIQUEIDENTIFIER NOT NULL,
        uploaded_at    DATETIME2(3)     NOT NULL DEFAULT SYSUTCDATETIME(),
        reviewed_by    UNIQUEIDENTIFIER NULL,
        reviewed_at    DATETIME2(3)     NULL,
        saved_at       DATETIME2(3)     NULL,

        created_at    DATETIME2(3)     NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at    DATETIME2(3)     NULL,

        is_deleted    BIT              NOT NULL DEFAULT 0,
        deleted_at    DATETIME2(3)     NULL,
        deleted_by    UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (import_id),
        UNIQUE (import_guid),
        FOREIGN KEY (duplicate_of_import_id) REFERENCES dbo.doc_import (import_id)
    );

    CREATE INDEX IX_doc_import_status
        ON dbo.doc_import (status)
        WHERE is_deleted = 0;

    CREATE INDEX IX_doc_import_tenant_store_uploaded
        ON dbo.doc_import (tenant_id, store_id, uploaded_at DESC)
        WHERE is_deleted = 0;

    CREATE INDEX IX_doc_import_created
        ON dbo.doc_import (created_at);

    /* duplicate-invoice validation rule */
    CREATE INDEX IX_doc_import_gst_invoice_dup
        ON dbo.doc_import (gst_number, invoice_number, invoice_date);

    CREATE INDEX IX_doc_import_invoice_date
        ON dbo.doc_import (invoice_date);

    CREATE INDEX IX_doc_import_supplier_code
        ON dbo.doc_import (matched_supplier_code);

    CREATE INDEX IX_doc_import_checksum
        ON dbo.doc_import (original_file_checksum)
        WHERE original_file_checksum IS NOT NULL;
END
GO

/* =============================================================================
   2. doc_product_mapping — resolves OCR product names to a stable internal
      ProductCode so future invoices reuse the same code instead of creating
      a duplicate. Lookup key is (supplier_code, normalized_product_key);
      supplier_code NULL = global fallback bucket.

      Workflow: normalize OCR product name -> look up here by
      (supplier_code, normalized_product_key) -> if found, reuse
      product_code; if not, INSERT here (this row IS the creation of the new
      mapping) and use the newly generated product_code.

      product_code is a PERSISTED computed column (DOC + 9-digit zero-padded
      id, e.g. DOC000000001) — race-condition-free, always unique, no
      app-side generation logic needed.
============================================================================= */
IF OBJECT_ID('dbo.doc_product_mapping', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.doc_product_mapping
    (
        product_mapping_id   BIGINT IDENTITY(1,1) NOT NULL,
        product_guid         UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        product_code         AS ('DOC' + RIGHT('000000000' + CONVERT(NVARCHAR(10), product_mapping_id), 9)) PERSISTED,

        tenant_id             UNIQUEIDENTIFIER NOT NULL,
        supplier_code         NVARCHAR(50)     NULL,   /* NULL = global fallback */

        ocr_product_name             NVARCHAR(300)    NOT NULL,
        normalized_product_name       NVARCHAR(300)    NOT NULL,
        normalized_product_key         NVARCHAR(300)    NOT NULL,

        match_count      INT              NOT NULL DEFAULT 1,   /* how many invoice lines have reused this mapping */
        is_active          BIT              NOT NULL DEFAULT 1,

        created_at   DATETIME2(3)     NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at    DATETIME2(3)     NULL,

        PRIMARY KEY (product_mapping_id),
        UNIQUE (product_guid)
    );

    /* never create duplicate mappings */
    CREATE UNIQUE INDEX UX_doc_product_mapping_supplier_key
        ON dbo.doc_product_mapping (supplier_code, normalized_product_key)
        WHERE supplier_code IS NOT NULL AND is_active = 1;

    CREATE UNIQUE INDEX UX_doc_product_mapping_global_key
        ON dbo.doc_product_mapping (normalized_product_key)
        WHERE supplier_code IS NULL AND is_active = 1;

    CREATE INDEX IX_doc_product_mapping_normalized_key
        ON dbo.doc_product_mapping (normalized_product_key);

    CREATE UNIQUE INDEX UX_doc_product_mapping_code
        ON dbo.doc_product_mapping (product_code);
END
GO

/* =============================================================================
   3. doc_import_item — one row per extracted medicine line.
============================================================================= */
IF OBJECT_ID('dbo.doc_import_item', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.doc_import_item
    (
        item_id           BIGINT IDENTITY(1,1) NOT NULL,
        tenant_id         UNIQUEIDENTIFIER NOT NULL,
        import_id         BIGINT           NOT NULL,

        line_number       INT              NOT NULL,

        product_code      NVARCHAR(20)     NULL,   /* from doc_product_mapping, once resolved */
        product_guid      UNIQUEIDENTIFIER NULL,

        ocr_product_name          NVARCHAR(300)    NOT NULL,
        normalized_product_name   NVARCHAR(300)    NULL,

        pack              NVARCHAR(50)     NULL,
        hsn_code          NVARCHAR(20)     NULL,
        batch_number      NVARCHAR(50)     NULL,
        expiry_raw        NVARCHAR(20)     NULL,
        expiry_date       DATE             NULL,

        quantity          DECIMAL(18,3)    NULL,
        free_quantity     DECIMAL(18,3)    NULL,
        ptr               DECIMAL(18,4)    NULL,
        purchase_rate     DECIMAL(18,4)    NULL,
        mrp               DECIMAL(18,4)    NULL,
        gst_percent       DECIMAL(5,2)     NULL,
        discount_percent  DECIMAL(5,2)     NULL,
        discount_amount   DECIMAL(18,2)    NULL,
        amount            DECIMAL(18,2)    NULL,

        confidence        DECIMAL(5,2)     NULL,
        is_excluded       BIT              NOT NULL DEFAULT 0,   /* mis-parsed row (banner/bank-details text), kept not deleted */

        created_at        DATETIME2(3)     NOT NULL DEFAULT SYSUTCDATETIME(),
        updated_at        DATETIME2(3)     NULL,

        PRIMARY KEY (item_id),
        FOREIGN KEY (import_id) REFERENCES dbo.doc_import (import_id),
        FOREIGN KEY (product_code) REFERENCES dbo.doc_product_mapping (product_code),
        UNIQUE (import_id, line_number)
    );

    CREATE INDEX IX_doc_import_item_import
        ON dbo.doc_import_item (import_id);

    CREATE INDEX IX_doc_import_item_normalized_name
        ON dbo.doc_import_item (normalized_product_name);

    CREATE INDEX IX_doc_import_item_product_code
        ON dbo.doc_import_item (product_code);
END
GO

/* =============================================================================
   4. doc_import_review — manual field corrections only. Not a general audit
      log: it exists so the Review UI can show "what did the user change"
      and nothing else. item_id NULL = header-level correction.
============================================================================= */
IF OBJECT_ID('dbo.doc_import_review', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.doc_import_review
    (
        review_id       BIGINT IDENTITY(1,1) NOT NULL,
        tenant_id       UNIQUEIDENTIFIER NOT NULL,
        import_id       BIGINT           NOT NULL,
        item_id         BIGINT           NULL,

        field_name      NVARCHAR(100)    NOT NULL,
        old_value       NVARCHAR(500)    NULL,
        new_value       NVARCHAR(500)    NULL,

        corrected_by    UNIQUEIDENTIFIER NOT NULL,
        corrected_at    DATETIME2(3)     NOT NULL DEFAULT SYSUTCDATETIME(),

        PRIMARY KEY (review_id),
        FOREIGN KEY (import_id) REFERENCES dbo.doc_import (import_id),
        FOREIGN KEY (item_id) REFERENCES dbo.doc_import_item (item_id)
    );

    CREATE INDEX IX_doc_import_review_import
        ON dbo.doc_import_review (import_id, corrected_at DESC);
END
GO

/* =============================================================================
   5. doc_export_history — export history log.
      file_format: XLSX / CSV
============================================================================= */
IF OBJECT_ID('dbo.doc_export_history', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.doc_export_history
    (
        export_id          BIGINT IDENTITY(1,1) NOT NULL,
        tenant_id          UNIQUEIDENTIFIER NOT NULL,
        export_batch_id    UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID(),
        import_id          BIGINT           NOT NULL,

        file_format        NVARCHAR(10)     NOT NULL,
        storage_path       NVARCHAR(1000)   NULL,
        row_count          INT              NULL,

        exported_by        UNIQUEIDENTIFIER NOT NULL,
        exported_at        DATETIME2(3)     NOT NULL DEFAULT SYSUTCDATETIME(),

        PRIMARY KEY (export_id),
        FOREIGN KEY (import_id) REFERENCES dbo.doc_import (import_id)
    );

    CREATE INDEX IX_doc_export_history_batch
        ON dbo.doc_export_history (export_batch_id);

    CREATE INDEX IX_doc_export_history_import
        ON dbo.doc_export_history (import_id, exported_at DESC);
END
GO

/* =============================================================================
   6. doc_supplier_layout (optional) — supplier-specific extraction
      configuration (header label mapping + item column mapping) stored as
      one JSON blob per supplier, replacing what would otherwise be a
      template + template-header + template-column table trio.
      supplier_code NULL = global default layout.

      Example layout_json shape:
      {
        "header_fields": [ { "field": "INVOICE_NUMBER", "labels": ["Bill No & Page No", "Tax Inv No"] } ],
        "item_columns":  [ { "field": "PRODUCT_NAME", "labels": ["Description", "Product Name"] } ]
      }
============================================================================= */
IF OBJECT_ID('dbo.doc_supplier_layout', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.doc_supplier_layout
    (
        layout_id       BIGINT IDENTITY(1,1) NOT NULL,
        tenant_id       UNIQUEIDENTIFIER NOT NULL,
        supplier_code   NVARCHAR(50)     NULL,   /* NULL = global default */

        layout_name     NVARCHAR(150)    NOT NULL,
        layout_json     NVARCHAR(MAX)    NOT NULL,
        is_active       BIT              NOT NULL DEFAULT 1,

        created_at      DATETIME2(3)     NOT NULL DEFAULT SYSUTCDATETIME(),
        created_by      UNIQUEIDENTIFIER NULL,
        updated_at      DATETIME2(3)     NULL,
        updated_by      UNIQUEIDENTIFIER NULL,

        PRIMARY KEY (layout_id)
    );

    CREATE UNIQUE INDEX UX_doc_supplier_layout_supplier
        ON dbo.doc_supplier_layout (supplier_code)
        WHERE supplier_code IS NOT NULL AND is_active = 1;

    CREATE UNIQUE INDEX UX_doc_supplier_layout_global
        ON dbo.doc_supplier_layout (layout_name)
        WHERE supplier_code IS NULL AND is_active = 1;
END
GO

/* =============================================================================
   Register the Document Extraction module for RBAC (idempotent) — matches
   the self-registration pattern used by product_mapping's migration.
============================================================================= */
IF NOT EXISTS (SELECT 1 FROM dbo.modules WHERE module_code = 'DOCUMENT_EXTRACTION')
BEGIN
    INSERT INTO dbo.modules (module_id, module_code, module_name, description, is_active)
    VALUES (NEWID(), 'DOCUMENT_EXTRACTION', 'Document Extraction', 'Extracts structured header/line-item data from supplier purchase invoices (PDF/image) for review and Excel export.', 1);
END
GO
