# Document Extraction Engine — Database Schema (V1, simplified)

Status: Draft — frozen before coding begins (Chunk 1/2 deliverable)
Schema: `dbo` (matches the existing module convention)
Migration file: `backend/modules/document_extraction/sql/0001_document_extraction_tables.sql`
Table prefix: `doc_`

**Revision note:** an earlier draft of this schema had 18 tables (separate document-type, processing-job, page, file, header, OCR-raw, OCR-block, template, template-header, template-column, validation, review-session, and audit tables). It was rejected as over-engineered for a module whose entire job is Upload → OCR → Extract → Review → Store → Export. This document describes the replacement: **6 tables**, with JSON columns used wherever a separate table would have added structure the module doesn't need in V1.

This module is an invoice OCR extraction tool. It is explicitly **not** a document management platform, workflow engine, template engine, OCR platform, or audit platform — the schema below reflects that scope, not a generic document-processing framework.

---

## Entity relationship overview

```
doc_import (1) ──< doc_import_item ──< doc_import_review
      │                  │
      │                  └── product_code ──> doc_product_mapping
      │
      ├──< doc_import_review   (item_id NULL = header-level correction)
      └──< doc_export_history

doc_product_mapping — standalone registry, referenced by doc_import_item.product_code

doc_supplier_layout — standalone config, keyed by supplier_code (no FK; read by
                       the extraction service before doc_import rows exist)
```

Six tables. No page table, no file table, no OCR-block table, no header table, no validation table, no audit table, no template tables — each of those either (a) has exactly one instance per invoice in V1 and folds into `doc_import`, or (b) is variable-shaped data better expressed as JSON than as a rigid child table.

---

## 1. dbo.doc_import

**One row per invoice.** This is the whole document: file locations, raw OCR payload, every header field, supplier detection result, and validation outcome all live on this single row.

| Column | Type | Notes |
|---|---|---|
| import_id | BIGINT IDENTITY | PK |
| import_guid | UNIQUEIDENTIFIER | NOT NULL DEFAULT NEWID(), UNIQUE |
| tenant_id | UNIQUEIDENTIFIER | NOT NULL |
| store_id | UNIQUEIDENTIFIER | NULL |
| status | NVARCHAR(30) | NOT NULL DEFAULT `'UPLOADED'`. `UPLOADED`\|`OCR_RUNNING`\|`EXTRACTED`\|`REVIEW_PENDING`\|`SAVED`\|`EXPORTED`\|`FAILED` |
| failure_reason | NVARCHAR(500) | NULL |
| is_upload_completed … is_exported | BIT | NOT NULL DEFAULT 0, one per pipeline stage (`is_upload_completed`, `is_image_processed`, `is_ocr_completed`, `is_header_extracted`, `is_items_extracted`, `is_reviewed`, `is_exported`). A fast bit-level progress readout kept in sync alongside `status`, so the Processing Queue UI can render a 7-step progress indicator without parsing state-machine strings |
| source_type | NVARCHAR(20) | NOT NULL. `PDF`\|`JPG`\|`JPEG`\|`PNG`\|`TIFF`\|`CAMERA` |
| original_file_path | NVARCHAR(1000) | NOT NULL. The primary/first page's path, kept for quick access |
| original_file_checksum | CHAR(64) | NULL — SHA-256 of the uploaded bytes, used for upload-time duplicate detection |
| original_files_json | NVARCHAR(MAX) | NULL — the authoritative structured page list (**OriginalFiles** contract, see `Document_Extraction_JSON_Contracts.md`); every element carries page number, original filename, storage path, display order, rotation, processing status |
| processed_files_json | NVARCHAR(MAX) | NULL until Chunk 5 — the **ProcessedFiles** contract, one entry per page after preprocessing |
| preview_image_path | NVARCHAR(1000) | NULL |
| page_count | INT | NULL |
| ocr_json | NVARCHAR(MAX) | NULL — the **OCRResult** contract: the *normalized* OCR model for the whole document (all pages), never the raw PaddleOCR response verbatim (see § OCR output contract). Replaces the separate OCR-raw/OCR-block tables from the discarded draft |
| ocr_confidence | DECIMAL(5,2) | NULL |
| ocr_supplier_name / supplier_name | NVARCHAR(200) | raw OCR value / matched final value |
| gst_number | NVARCHAR(20) | NULL |
| dl_number | NVARCHAR(50) | NULL |
| supplier_phone | NVARCHAR(20) | NULL |
| supplier_address | NVARCHAR(500) | NULL |
| matched_supplier_code | NVARCHAR(50) | NULL — loose reference into the existing supplier master (no FK, different schema) |
| supplier_match_method | NVARCHAR(20) | NULL. `GST`\|`DL`\|`PHONE`\|`NAME`\|`MANUAL`\|`UNKNOWN` |
| supplier_match_confidence | DECIMAL(5,2) | NULL |
| is_supplier_unknown | BIT | NOT NULL DEFAULT 0 |
| ocr_invoice_number / invoice_number | NVARCHAR(50) | raw / parsed |
| ocr_invoice_date / invoice_date | NVARCHAR(20) / DATE | raw text / parsed |
| invoice_type, order_number, transport, salesman, credit_days | — | header fields |
| gross_amount … total_quantity | DECIMAL/INT | full header total block (gross, discount, scheme discount, cash discount, taxable, CGST, SGST, IGST, CESS, round off, net, item count, total qty) |
| irn_number, ack_number, ack_date | — | optional e-invoice fields |
| gst_slab_breakup_json | NVARCHAR(MAX) | NULL — variable-length GST slab rows (0%/5%/12%/18%/28%, each with taxable/CGST/SGST/total); real invoices report a variable number of slabs (see Sample B in the Design doc), so this is JSON rather than a rigid column set |
| validation_status | NVARCHAR(20) | NOT NULL DEFAULT `'PENDING'`. `PENDING`\|`PASSED`\|`WARNING`\|`FAILED` |
| validation_json | NVARCHAR(MAX) | NULL — the **Validation** contract: array of `{rule_code, severity, field, message}` findings. Replaces the separate validation table |
| latest_export_json | NVARCHAR(MAX) | NULL — the **ExportInfo** contract: a denormalized copy of the most recent `doc_export_history` row, so Review/History can show "last exported" without a join. `doc_export_history` remains the authoritative full list |
| is_duplicate | BIT | NOT NULL DEFAULT 0 |
| duplicate_of_import_id | BIGINT | NULL, self-FK |
| uploaded_by / uploaded_at | UNIQUEIDENTIFIER / DATETIME2(3) | NOT NULL |
| reviewed_by / reviewed_at | UNIQUEIDENTIFIER / DATETIME2(3) | NULL until review completes |
| saved_at | DATETIME2(3) | NULL until `status = SAVED` |
| created_at / updated_at | DATETIME2(3) | audit |
| is_deleted / deleted_at / deleted_by | BIT / DATETIME2(3) / UNIQUEIDENTIFIER | soft delete |

Indexes: `status` (filtered, live rows), `(tenant_id, store_id, uploaded_at DESC)` (filtered), `created_at`, `(gst_number, invoice_number, invoice_date)` (duplicate check), `invoice_date`, `matched_supplier_code`.

**Why folding header/supplier/validation into one row is correct here:** every one of those is a strict 1:1 relationship with the invoice in V1 (one header, one supplier match, one validation outcome per document). A join only earns its cost when the child side is 0:N or independently queried at scale — none of these are. If a future version needs per-attempt validation history or multi-supplier candidates, that's a schema change made when the requirement actually shows up, not speculative now.

---

## 2. dbo.doc_product_mapping

Deduplicated internal ProductCode registry — the answer to "ProductCode is usually missing in supplier invoices."

**Workflow:** normalize OCR product name → look up by `(supplier_code, normalized_product_key)` → if found, reuse `product_code`; if not, this row **is** the creation of the new mapping, and its computed `product_code` is the newly generated code. `supplier_code = NULL` is the global fallback bucket for products not yet tied to a resolved supplier.

| Column | Type | Notes |
|---|---|---|
| product_mapping_id | BIGINT IDENTITY | PK |
| product_guid | UNIQUEIDENTIFIER | NOT NULL DEFAULT NEWID(), UNIQUE |
| product_code | *(computed, PERSISTED)* | `'DOC' + RIGHT('000000000' + CONVERT(NVARCHAR(10), product_mapping_id), 9)` → e.g. `DOC000000001`. Derived from the identity value, so it's race-condition-free and unique with no app-side generation logic |
| tenant_id | UNIQUEIDENTIFIER | NOT NULL |
| supplier_code | NVARCHAR(50) | NULL = global fallback |
| ocr_product_name | NVARCHAR(300) | NOT NULL — representative OCR text that first created this mapping |
| normalized_product_name | NVARCHAR(300) | NOT NULL |
| normalized_product_key | NVARCHAR(300) | NOT NULL — the dedup lookup key |
| match_count | INT | NOT NULL DEFAULT 1 — how many invoice lines have reused this mapping |
| is_active | BIT | NOT NULL DEFAULT 1 |
| created_at / updated_at | DATETIME2(3) | |

**Never create duplicate mappings** is enforced by two filtered unique indexes (not app-layer discipline alone):
- `UX_doc_product_mapping_supplier_key` on `(supplier_code, normalized_product_key)` WHERE `supplier_code IS NOT NULL AND is_active = 1`
- `UX_doc_product_mapping_global_key` on `(normalized_product_key)` WHERE `supplier_code IS NULL AND is_active = 1`

Plus `UX_doc_product_mapping_code` (unique) and `IX_doc_product_mapping_normalized_key`.

---

## 3. dbo.doc_import_item

One row per extracted medicine line.

| Column | Type | Notes |
|---|---|---|
| item_id | BIGINT IDENTITY | PK |
| import_id | BIGINT | NOT NULL, FK → doc_import |
| line_number | INT | NOT NULL |
| product_code | NVARCHAR(20) | NULL, FK → doc_product_mapping(product_code) — set once resolution runs |
| product_guid | UNIQUEIDENTIFIER | NULL — denormalized copy of the mapping's GUID |
| ocr_product_name | NVARCHAR(300) | NOT NULL |
| normalized_product_name | NVARCHAR(300) | NULL |
| pack, hsn_code, batch_number | NVARCHAR | line fields |
| expiry_raw / expiry_date | NVARCHAR(20) / DATE | raw text / parsed |
| quantity, free_quantity | DECIMAL(18,3) | |
| ptr, purchase_rate, mrp | DECIMAL(18,4) | |
| gst_percent, discount_percent | DECIMAL(5,2) | |
| discount_amount, amount | DECIMAL(18,2) | |
| confidence | DECIMAL(5,2) | NULL |
| is_excluded | BIT | NOT NULL DEFAULT 0 — user-marked mis-parsed row (banner/bank-details text a table parser swept up); kept, never hard-deleted |
| created_at / updated_at | DATETIME2(3) | |

Constraint: UNIQUE `(import_id, line_number)`. Indexes: `import_id`, `normalized_product_name`, `product_code`.

---

## 4. dbo.doc_import_review

Manual field corrections only — **not** a general audit log. Exists so the Review UI can show "what did the user change," nothing more.

| Column | Type | Notes |
|---|---|---|
| review_id | BIGINT IDENTITY | PK |
| import_id | BIGINT | NOT NULL, FK → doc_import |
| item_id | BIGINT | NULL, FK → doc_import_item — NULL means a header-level field correction |
| field_name | NVARCHAR(100) | NOT NULL |
| old_value / new_value | NVARCHAR(500) | NULL |
| corrected_by | UNIQUEIDENTIFIER | NOT NULL |
| corrected_at | DATETIME2(3) | NOT NULL DEFAULT SYSUTCDATETIME() |

Index: `(import_id, corrected_at DESC)`.

Who uploaded / reviewed / exported an invoice is answered directly from `doc_import.uploaded_by/reviewed_by` and `doc_export_history.exported_by` — a separate generic audit table would only duplicate that.

---

## 5. dbo.doc_export_history

Export history log.

| Column | Type | Notes |
|---|---|---|
| export_id | BIGINT IDENTITY | PK |
| export_batch_id | UNIQUEIDENTIFIER | NOT NULL DEFAULT NEWID() — groups a multi-invoice export |
| import_id | BIGINT | NOT NULL, FK → doc_import |
| file_format | NVARCHAR(10) | NOT NULL. `XLSX`\|`CSV` |
| storage_path | NVARCHAR(1000) | NULL |
| row_count | INT | NULL |
| exported_by / exported_at | UNIQUEIDENTIFIER / DATETIME2(3) | NOT NULL |

Indexes: `export_batch_id`, `(import_id, exported_at DESC)`.

---

## 6. dbo.doc_supplier_layout (optional)

Supplier-specific extraction configuration — header label mapping + item column mapping — as **one JSON blob per supplier**, replacing what would otherwise be a template/template-header/template-column table trio. `supplier_code = NULL` is the global default layout.

| Column | Type | Notes |
|---|---|---|
| layout_id | BIGINT IDENTITY | PK |
| tenant_id | UNIQUEIDENTIFIER | NOT NULL |
| supplier_code | NVARCHAR(50) | NULL = global default |
| layout_name | NVARCHAR(150) | NOT NULL |
| layout_json | NVARCHAR(MAX) | NOT NULL |
| is_active | BIT | NOT NULL DEFAULT 1 |
| created_at/by, updated_at/by | — | audit |

Example `layout_json`:
```json
{
  "header_fields": [ { "field": "INVOICE_NUMBER", "labels": ["Bill No & Page No", "Tax Inv No"] } ],
  "item_columns":  [ { "field": "PRODUCT_NAME", "labels": ["Description", "Product Name"] } ]
}
```

Filtered unique indexes enforce one active layout per supplier and one active global default, same dual-filtered-index pattern used elsewhere in the platform (`product_normalization_dictionary`).

---

## File storage

Unchanged in spirit from the original design, simplified to match the flatter schema: `data/document_extraction/{import_id}/original/…`, `preview/…`, `export/{export_batch_id}.xlsx`. `doc_import.original_file_path`/`preview_image_path` point into this tree. A multi-image upload that represents one invoice stores its paths as a JSON array string in `original_file_path` rather than needing a `doc_file` table.

## What got cut, and why it's safe to cut

| Removed | Replaced by |
|---|---|
| doc_document_type | Dropped — V1 only ever extracts invoices; `source_type` still records the file format |
| doc_processing_job | Dropped — pipeline stage timing goes through the existing platform logging pipeline (unchanged), not a DB table |
| doc_page / doc_file | `page_count` + `original_file_path`/`preview_image_path` on `doc_import` |
| doc_ocr_raw / doc_ocr_block | `ocr_json` on `doc_import` |
| doc_header / doc_supplier_match | Folded into `doc_import` (1:1 in V1) |
| doc_validation | `validation_status` + `validation_json` on `doc_import` |
| doc_review (session) / doc_audit | `doc_import_review` (corrections only) + `uploaded_by`/`reviewed_by`/`exported_by` columns |
| doc_template / doc_template_header / doc_template_column | `doc_supplier_layout.layout_json` |

If a real V1 requirement later needs one of these back (e.g. per-page rotation angles once multi-page handling gets built out, or bounding-box-level OCR review), it gets added then, against an actual need — not spread across the schema up front.
