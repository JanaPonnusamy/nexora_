# Document Extraction Engine — Design (V1)

Status: Draft — frozen before coding begins (Chunk 1 deliverable)
Module: `document_extraction` (new, standalone)
Owner scope: extraction + review + Excel export only. **No purchase posting, no ERP integration, no accounting, no inventory update.**

> Note: `Project_Master_Document.md` referenced by the build instructions does not exist in this repository. This document set treats the module brief supplied by the user as the source specification and cross-references it below. If a `Project_Master_Document.md` is added later, reconcile against it.

Companion frozen documents: `Document_Extraction_Database.md`, `Document_Extraction_API.md`, `Document_Extraction_UI.md`, `Document_Extraction_Workflow.md`, `Document_Extraction_DevelopmentPlan.md`, `Document_Extraction_JSON_Contracts.md`, `Document_Extraction_Excel_Contract.md`.

---

## 1. Purpose

Extract structured header + line-item data from supplier purchase invoices (PDF, JPG, PNG, TIFF, mobile camera photos), let a user review/correct the extraction, persist it, and export it as Excel/CSV formatted for import into third-party pharmacy software.

## 2. Why a standalone module

- Reuses platform conventions (FastAPI backend, SQL Server via `dbo` schema, flat per-module file layout, React frontend) but owns its own tables, router, and pages.
- Does not touch `procurement.*`, `sync.*`, auth, or logging infrastructure. It is additive: a new `backend/modules/document_extraction/` package and a new `/document-extraction` frontend route, mounted alongside existing modules the same way `product_mapping` and `reports` are.
- No write path into `sync.PurchaseTrans` or any procurement table exists in V1. The only output artifact is the Excel/CSV file plus the module's own review tables.

## 3. Reference: real supplier invoice variability

Four sample invoices were inspected (`assects/sample invoice/*.jpeg`) to ground the design in real documents rather than an idealized layout:

**Sample A — Nathan Medicals -C** (single-page, portrait, clean grid)
- Header fields present: supplier name/address, State Code, State Name, GSTIN, DL No, Bill No & Page No, Bill Date, Order Date, Order No, Salesman Name/Phone, Delivery Type, Terms (e.g. "D-CREDIT BILL").
- Item table columns: S No, Description, Pack, HSN/SAC, Batch No., Exp, S.U, Qty, Free, PDis, PTR, MRP, GST Base, GST%, Total.
- Footer: Items count, total Qty, Base, SGST, CGST, GST, Amount; a GST-category breakup table (rate → Base/CGST/SGST/Amount); Round Off; Rounded Net Amount; Amount in Words; Terms & Conditions text.

**Sample B — Thanthai Pharma Distributor** (multi-page, landscape/rotated scan, dense grid, e-invoice)
- Header fields: GST Tax Invoice, Code, Inv Date, GSTIN, DL No, Ph No, Tax Invoice No, Transport, Sales Rep, plus e-invoice **IRN No / Ack No / Ack Date** and a QR code.
- Item table columns differ entirely from Sample A: Loc, Code, Hsn, Batch, Exp Date, MRP, Product Name, Pack, Qty, FR (free), Trade Price, Product Value, Sch Disc%, Cash Disc%, Tax, GST%.
- Multi-slab GST breakup (0%/5%/12%/18%/28% rows, each with Taxable/CGST/SGST/GST-Total/Net).
- Multi-page continuation: pages are numbered "Page No: 1/3, 2/3, 3/3" with a "Continue…" marker and repeated header block; a "Pending Order" column and an "Expiry Stock Do Not Return Back" banner appear mid-page and must not be parsed as line items.
- Bank details block (account no., IFSC, branch) present on the page — explicitly **out of scope**, must be ignored by extraction.
- Physical scan artifacts: page rotated ~90°, handwritten ticks/checkmarks over printed rows, ink smudges, staple holes.

**Design implications (binding):**
1. Column layout is **not fixed** — the column-mapping/normalization layer (§ Normalization in the workflow doc) is mandatory from V1, not a future enhancement, because two real suppliers already disagree on every column name and order.
2. Multi-page invoices must be **stitched**: header is authoritative from page 1 only; item rows accumulate across pages; continuation banners/watermarks ("EXPIRY STOCK DO NOT RETURN BACK", "Rapid News", bank details) must be filtered out by the line-item classifier, not treated as extraction errors.
3. Preprocessing must handle arbitrary page rotation (not just skew) since whole pages arrive rotated 90°.
4. GST breakup is slab-wise (multiple rows), not a single CGST/SGST pair — the header extraction schema stores a repeating GST-slab structure, not fixed columns.
5. E-invoice fields (IRN, Ack No, Ack Date) exist on some suppliers and not others — treated as optional header fields, never required for validation to pass.

## 4. Scope boundaries (hard constraints)

| In scope | Out of scope |
|---|---|
| Upload, OCR, header/item extraction, supplier detection, validation, user review/correction, persistence, Excel/CSV export, history, correction tracking, reprocessing | Posting to purchase/inventory tables, GRN creation, supplier ledger updates, accounting entries, ERP/API push to third-party pharmacy software (only file export), authentication changes, changes to existing logging pipeline, general-purpose document audit trail |

## 5. High-level architecture

```
Frontend (React, /document-extraction/*)
   │  REST (JSON) + multipart upload
   ▼
Backend module: backend/modules/document_extraction/
   router.py        — FastAPI routes (thin)
   service.py        — orchestration: upload → preprocess → OCR → extract → validate
   preprocessing.py  — rotate/deskew/crop/denoise/threshold, PDF page split (in-process; only the
                        final original + preview images are persisted, not a table per page)
   ocr_engine.py      — PaddleOCR wrapper, writes the whole-document result to doc_import.ocr_json
   supplier_detect.py — GST/DL/phone/name matching against doc_import's own supplier columns +
                        existing supplier master
   header_extract.py  — header field parser over the OCR result
   item_extract.py    — table/line-item parser over the OCR result
   normalization.py   — column-mapping sourced from doc_supplier_layout.layout_json (per-supplier
                        + global default)
   validation.py      — totals/duplicate/missing-field/confidence checks, writes validation_json
   export_excel.py    — openpyxl workbook builder
   repository.py      — SQLAlchemy/pyodbc data access
   schemas.py          — Pydantic request/response models
   sql/0001_document_extraction_tables.sql
Storage: local disk store for originals, previews, exports (see § File Storage)
Database: SQL Server, dbo schema, 6 doc_* tables (see Document_Extraction_Database.md)
```

This mirrors the existing `product_mapping` module's flat-file layout (`router.py`, `service.py`, `repository.py`, `schemas.py`, `sql/`) — no new architectural pattern introduced. **Note:** an earlier version of this design had a table per pipeline artifact (page, file, OCR block, header, template, processing job, validation, audit). That was rejected as over-engineered for a module whose job is Upload → OCR → Extract → Review → Store → Export — the schema was cut to 6 tables (Database doc), and this section has been updated to match: preprocessing and OCR still happen as code steps, they just don't each get a dedicated persistence table.

## 6. Processing pipeline (summary — full detail in Workflow doc)

Upload → Image Processing → OCR → Supplier Detection → Header Extraction → Product Extraction → Validation → User Review → Store Database → Excel Export.

These are code-level steps within one service call chain, not separate persisted job records — `doc_import.status` is the single state machine tracking progress (see Database doc), and a failure at any step sets `status = FAILED` with `failure_reason` set, without a per-stage table to reconcile.

## 7. Image input & preprocessing

Accepted inputs: PDF (single/multi-page), JPEG, JPG, PNG, TIFF, multiple images per invoice, mobile camera photos.

Multiple files/pages that represent one invoice (multi-page PDF, several JPGs from a phone camera, or a mix) are always **one import session** — one `doc_import` row, never one row per file. Page order and per-page state are tracked via the `OriginalFiles` → `ProcessedFiles` JSON contracts (`docs/Document_Extraction_JSON_Contracts.md` §1–2), not a `doc_page` table.

Automatic preprocessing steps (in order): PDF page split → page-orientation detection → rotate → deskew → crop borders → shadow removal → noise removal → contrast enhancement → adaptive threshold. Each page's result is recorded as one entry in `processed_files_json` (the `ProcessedFiles` contract); a single preview rendition is also set on `doc_import.preview_image_path` for quick access. Intermediate raster buffers are working memory during the pipeline call, not individually tracked rows.

## 8. OCR engine and OCR output contract

PaddleOCR is the OCR engine, but **its raw response never reaches storage or extraction logic directly.** This separation is mandatory, not an optimization:

```
PaddleOCR raw response → normalize → OCRResult (docs/Document_Extraction_JSON_Contracts.md §3)
                                    → stored in doc_import.ocr_json
                                    → Invoice Parser (header_extract.py / item_extract.py)
                                    → Business Model (doc_import header fields / doc_import_item rows)
```

A normalization step converts whatever shape the engine actually returns into the frozen `OCRResult` contract (engine name/version, pages → lines → words, each with text/confidence/bounding-box) before anything else touches it. Header/item extraction (Chunks 8–9) reads only `OCRResult`, never an engine-specific payload. This is what lets extraction logic be re-run against the same OCR output without re-running OCR (§ Reprocess, Workflow doc), lets a future OCR engine swap stay isolated to the normalization step, and lets a human compare "what OCR saw" against "what got interpreted" without needing to know PaddleOCR's own response format.

## 9. Supplier identification

Matched in priority order: **GST Number → DL Number → Phone → Supplier Name** (fuzzy, using `rapidfuzz` which is already a project dependency). First match wins. If no match clears the confidence threshold, the invoice is tagged `Unknown Supplier` (`doc_import.is_supplier_unknown = 1`) and routed to manual assignment in the Review UI rather than blocking the pipeline.

## 10. Header extraction

Fields: Supplier Name, GST Number, DL Number, Invoice Number, Invoice Date, Invoice Type, Order Number, Transport, Salesman, Credit Days, Gross Amount, Discount, Scheme Discount, Cash Discount, Taxable Amount, CGST, SGST, IGST, CESS (per-slab, repeating, stored as `gst_slab_breakup_json`), Round Off, Net Amount, Item Count, Total Quantity. Optional e-invoice fields (IRN No, Ack No, Ack Date) captured when present, never required. All written directly onto `doc_import`.

## 11. Product extraction

Fields per line: Product Name, Pack, HSN, Batch, Expiry, Quantity, Free Quantity, PTR, Purchase Rate, MRP, GST, Discount, Amount — written to `doc_import_item`, one row per line.

## 12. Normalization

A configurable column-mapping, stored as JSON on `doc_supplier_layout.layout_json` (keyed by detected supplier + a global-default row), maps source column headers to canonical fields, e.g. `Description|Medicine|Item|Drug → Product Name`, `PTR|Trade Rate|Purchase Rate → Purchase Price`. This is what makes Sample A's and Sample B's completely different column sets converge on one internal schema. JSON was chosen over a template/template-column table pair because the mapping is read whole (never queried relationally) and edited whole (Settings page saves the entire JSON blob for a supplier at once).

## 13. Validation rules

Invoice Total reconciliation, GST Total reconciliation, Item Total reconciliation, duplicate invoice detection (supplier + invoice number + date), missing batch, missing expiry, low OCR confidence flag. Validation never blocks save — findings are written as a JSON array to `doc_import.validation_json` (with `validation_status` summarizing PASSED/WARNING/FAILED) and surfaced in the Review UI; the user decides whether to save anyway.

## 14. User review

Header panel (Supplier, Invoice Number, Date, Amount, Status, Confidence) + editable line-item grid (Product, Batch, Expiry, Qty, Free, PTR, MRP, GST, Amount, Confidence). Missing fields and low-confidence cells are visually highlighted. Every field edit is captured as one row in `doc_import_review` (field name, old value, new value, who, when) — that table exists solely to answer "what did the user change," it is not a general-purpose audit log.

## 15. Excel export

Primary deliverable. One workbook per export with 5 sheets: Invoice Header (from `doc_import`'s header columns), Products (from `doc_import_item`, excluding `is_excluded = 1` rows), GST Summary (from `gst_slab_breakup_json`), Validation Errors (from `validation_json`), OCR Metadata (confidence summary from `ocr_confidence`/`overall_confidence` — not a bounding-box dump, since bounding boxes aren't persisted in V1). `xlsx` and `csv` supported (csv covers Sheet 2 — Products — only, since csv is single-table).

## 16. Non-functional requirements

- Schema and indexing must support millions of documents (see Database doc — clustered/nonclustered index strategy, partitioning-ready design).
- Every stage logs Start Time, End Time, Duration, Pages, Products, Confidence, Errors (existing platform logging pipeline — not modified, only used).
- Errors (corrupted PDF, unreadable image, OCR failure, missing header, broken table, invalid invoice, DB failure) degrade gracefully: the pipeline marks the document's stage as `failed` with a reason and stops advancing that document, it never crashes the request or blocks other documents.

## 16b. File storage

Files are written to a module-owned storage root (local disk path in V1, e.g. `data/document_extraction/`, matching the platform's existing local-disk convention for generated artifacts — no new blob-storage dependency introduced). Layout, one folder per import to keep everything for a document co-located and trivially purgeable:

```
data/document_extraction/{import_id}/
  original/    — as-uploaded file(s), unmodified
  preview/     — preview rendition(s) for the Review UI page pane
data/document_extraction/_exports/{export_batch_id}.xlsx — generated export workbooks
```

Exports live outside any single import's folder (`_exports/`, not `{import_id}/export/`) because one export batch can cover several invoices at once (§ API doc §7) — filing it under one import's directory would be misleading for a multi-invoice export. `doc_export_history.storage_path` records where each batch landed.

No per-page processed-image folder and no per-page OCR JSON files — the preprocessed image is a working artifact of the pipeline call, not persisted separately from the preview, and the raw OCR result is stored directly in `doc_import.ocr_json`, not mirrored to disk. `doc_import.original_file_path` / `preview_image_path` store paths relative to this root (a JSON array string when a multi-image upload represents one invoice). Physical files are never deleted on a soft-delete (§ Database doc); a separate retention/purge job is out of scope for V1.

## 17. Explicit non-goals for V1

No purchase posting, no ERP integration, no accounting entries, no inventory update, no automatic supplier-master writes (new suppliers are proposed, not auto-created), no changes to authentication or existing logging.
